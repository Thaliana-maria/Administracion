from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from auditlog.services import registrar_cambio
from expenses.models import Asignacion, Compra, Item, Membresia
from expenses.services.ajustes import recalcular_ajustes_compra
from expenses.services.permisos import exigir_puede_editar_compra
from ledger.models import Obligacion


def _exigir_sin_abonos(compra, asignaciones=None):
    obligaciones = Obligacion.objects.filter(
        asignacion__item__compra=compra,
        anulada=False,
        aplicaciones__anulada=False,
        aplicaciones__pago__anulada=False,
    )
    if asignaciones is not None:
        obligaciones = obligaciones.filter(asignacion__in=asignaciones)
    if obligaciones.exists():
        raise ValidationError(
            "No se puede modificar este registro mientras tenga pagos aplicados."
        )


def _datos_compra(compra):
    return {
        "fecha": compra.fecha.isoformat(),
        "total": str(compra.total),
        "impuesto": str(compra.impuesto),
        "descuento": str(compra.descuento),
        "descripcion": compra.descripcion,
    }


@transaction.atomic
def actualizar_compra(usuario, compra_id, *, fecha=None, total=None, descripcion=None):
    compra = Compra.objects.select_for_update().get(pk=compra_id)
    exigir_puede_editar_compra(compra, usuario)
    if compra.anulada:
        raise ValidationError("No se puede editar una compra anulada.")

    datos_anteriores = _datos_compra(compra)
    if fecha is not None:
        compra.fecha = fecha
    if descripcion is not None:
        compra.descripcion = descripcion
    if total is not None:
        nuevo_total = Decimal(str(total))
        if nuevo_total <= 0 or nuevo_total != nuevo_total.quantize(Decimal("0.01")):
            raise ValidationError("El total debe ser positivo y tener máximo dos decimales.")
        if nuevo_total != compra.total:
            _exigir_sin_abonos(compra)
            subtotal = Item.objects.filter(compra=compra, anulada=False).aggregate(
                total=models.Sum("valor")
            )["total"] or Decimal("0.00")
            if nuevo_total != subtotal + compra.impuesto - compra.descuento:
                raise ValidationError("El total de la compra debe coincidir con sus ítems.")
            compra.total = nuevo_total

    datos_nuevos = _datos_compra(compra)
    if datos_anteriores != datos_nuevos:
        compra.save()
        registrar_cambio(
            usuario,
            compra,
            "editar",
            {"antes": datos_anteriores, "despues": datos_nuevos},
        )
    return compra


@transaction.atomic
def actualizar_item(usuario, item_id, *, valor, asignaciones, descripcion=None):
    item = Item.objects.select_for_update().select_related("compra").get(pk=item_id)
    exigir_puede_editar_compra(item.compra, usuario)
    if item.anulada or item.compra.anulada:
        raise ValidationError("No se puede editar un ítem anulado.")

    valor_nuevo = Decimal(str(valor))
    if valor_nuevo <= 0 or valor_nuevo != valor_nuevo.quantize(Decimal("0.01")):
        raise ValidationError("El valor del ítem debe ser positivo y tener máximo dos decimales.")
    valores = {
        int(usuario_id): Decimal(str(monto))
        for usuario_id, monto in asignaciones.items()
    }
    if not valores or any(
        monto <= 0 or monto != monto.quantize(Decimal("0.01"))
        for monto in valores.values()
    ):
        raise ValidationError("Cada asignación debe ser positiva y tener máximo dos decimales.")
    if sum(valores.values(), Decimal("0.00")) != valor_nuevo:
        raise ValidationError("La suma de las asignaciones debe coincidir con el valor del ítem.")

    compra = Compra.objects.select_for_update().get(pk=item.compra_id)
    existentes = list(Asignacion.objects.select_for_update().filter(item=item, anulada=False))
    _exigir_sin_abonos(compra, existentes)
    datos_anteriores = {
        "descripcion": item.descripcion,
        "valor": str(item.valor),
        "compra_total": str(compra.total),
    }
    total_items = Item.objects.filter(compra=compra, anulada=False).aggregate(
        total=models.Sum("valor")
    )["total"] or Decimal("0.00")
    if compra.total != total_items + compra.impuesto - compra.descuento:
        raise ValidationError("El total actual de la compra no coincide con sus componentes.")
    compra.total += valor_nuevo - item.valor
    if compra.total <= 0:
        raise ValidationError("El total de la compra debe ser positivo.")
    compra.save(update_fields=["total"])
    item.valor = valor_nuevo
    if descripcion is not None:
        item.descripcion = descripcion
    item.save(update_fields=["valor", "descripcion"])
    _reemplazar_asignaciones(item, usuario, valores, existentes)
    recalcular_ajustes_compra(compra.pk)
    registrar_cambio(
        usuario,
        item,
        "editar",
        {
            "antes": datos_anteriores,
            "despues": {
                "descripcion": item.descripcion,
                "valor": str(item.valor),
                "compra_total": str(compra.total),
            },
        },
    )
    return item


@transaction.atomic
def actualizar_asignaciones(usuario, item_id, asignaciones):
    item = Item.objects.get(pk=item_id)
    return actualizar_item(
        usuario,
        item.pk,
        valor=item.valor,
        asignaciones=asignaciones,
    )


def _reemplazar_asignaciones(item, usuario, valores, existentes=None):
    miembros = set(
        Membresia.objects.filter(
            grupo_id=item.compra.grupo_id,
            usuario_id__in=valores,
            activo=True,
        ).values_list("usuario_id", flat=True)
    )
    if item.compra.grupo.creador_id in valores:
        miembros.add(item.compra.grupo.creador_id)
    if miembros != set(valores):
        raise ValidationError("Todos los beneficiarios deben pertenecer al grupo.")

    existentes = existentes or list(
        Asignacion.objects.select_for_update().filter(item=item, anulada=False)
    )
    ahora = timezone.now()
    anteriores = [
        {"beneficiario_id": row.beneficiario_id, "valor": str(row.valor_asignado)}
        for row in existentes
    ]
    for asignacion in existentes:
        asignacion.anulada = True
        asignacion.anulada_en = ahora
        asignacion.anulada_por = usuario
        asignacion.save(update_fields=["anulada", "anulada_en", "anulada_por"])

    nuevas = [
        Asignacion.objects.create(
            item=item,
            beneficiario_id=usuario_id,
            valor_asignado=valor,
        )
        for usuario_id, valor in sorted(valores.items())
    ]
    registrar_cambio(
        usuario,
        item,
        "editar_asignaciones",
        {
            "antes": anteriores,
            "despues": [
                {"beneficiario_id": row.beneficiario_id, "valor": str(row.valor_asignado)}
                for row in nuevas
            ],
        },
    )


@transaction.atomic
def anular_item(usuario, item_id):
    item = Item.objects.select_for_update().select_related("compra").get(pk=item_id)
    exigir_puede_editar_compra(item.compra, usuario)
    if item.anulada or item.compra.anulada:
        raise ValidationError("El ítem ya está anulado.")
    asignaciones = list(item.asignaciones.select_for_update().filter(anulada=False))
    _exigir_sin_abonos(item.compra, asignaciones)

    compra = Compra.objects.select_for_update().get(pk=item.compra_id)
    total_items = Item.objects.filter(compra=compra, anulada=False).aggregate(
        total=models.Sum("valor")
    )["total"] or Decimal("0.00")
    if compra.total != total_items + compra.impuesto - compra.descuento:
        raise ValidationError("El total actual de la compra no coincide con sus componentes.")
    if total_items == item.valor:
        raise ValidationError("Para anular el último ítem, debe anularse la compra completa.")

    ahora = timezone.now()
    total_anterior = compra.total
    compra.total -= item.valor
    if compra.total <= 0:
        raise ValidationError("La anulación dejaría el total de la compra en cero o negativo.")
    compra.save(update_fields=["total"])
    item.anulada = True
    item.anulada_en = ahora
    item.anulada_por = usuario
    item.save(update_fields=["anulada", "anulada_en", "anulada_por"])
    for asignacion in asignaciones:
        asignacion.anulada = True
        asignacion.anulada_en = ahora
        asignacion.anulada_por = usuario
        asignacion.save(update_fields=["anulada", "anulada_en", "anulada_por"])
    recalcular_ajustes_compra(compra.pk)
    registrar_cambio(
        usuario,
        item,
        "anular",
        {"valor": str(item.valor), "compra_total_despues": str(compra.total)},
    )
    registrar_cambio(
        usuario,
        compra,
        "actualizar_total_por_anulacion_de_item",
        {"total_antes": str(total_anterior), "total_despues": str(compra.total)},
    )
    return item


@transaction.atomic
def anular_compra(usuario, compra_id):
    compra = Compra.objects.select_for_update().get(pk=compra_id)
    exigir_puede_editar_compra(compra, usuario)
    if compra.anulada:
        raise ValidationError("La compra ya está anulada.")

    ahora = timezone.now()
    detalles_compra = _datos_compra(compra)
    compra.anulada = True
    compra.anulada_en = ahora
    compra.anulada_por = usuario
    compra.save(update_fields=["anulada", "anulada_en", "anulada_por"])
    registrar_cambio(usuario, compra, "anular", detalles_compra)
    Obligacion.objects.filter(asignacion__item__compra=compra, anulada=False).update(
        anulada=True
    )

    for item in compra.items.select_for_update().filter(anulada=False):
        item.anulada = True
        item.anulada_en = ahora
        item.anulada_por = usuario
        item.save(update_fields=["anulada", "anulada_en", "anulada_por"])
        registrar_cambio(usuario, item, "anular_por_compra", {"compra_id": compra.pk})
        for asignacion in item.asignaciones.select_for_update().filter(anulada=False):
            asignacion.anulada = True
            asignacion.anulada_en = ahora
            asignacion.anulada_por = usuario
            asignacion.save(update_fields=["anulada", "anulada_en", "anulada_por"])
            registrar_cambio(
                usuario,
                asignacion,
                "anular_por_compra",
                {"compra_id": compra.pk, "item_id": item.pk},
            )
    return compra

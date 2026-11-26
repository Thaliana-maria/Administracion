from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from auditlog.services import registrar_cambio
from expenses.models import Asignacion, Compra, Grupo, Item, Membresia, RevisionCompra
from expenses.services.ajustes import recalcular_ajustes_compra
from expenses.services.reparto import repartir
from expenses.services.permisos import exigir_puede_editar_compra
from ledger.models import Obligacion


def _exigir_sin_abonos(compra, asignaciones=None):
    from ledger.models import TramoCompensacion

    tramos = TramoCompensacion.objects.filter(obligacion__asignacion__item__compra=compra, compensacion__estado__in=["pendiente", "aprobada", "aplicada"])
    if asignaciones is not None:
        tramos = tramos.filter(obligacion__asignacion__in=asignaciones)
    if tramos.exists():
        raise ValidationError("La compra está vinculada a una compensación activa o aplicada.")

    obligaciones = Obligacion.objects.filter(
        asignacion__item__compra=compra,
        anulada=False,
        aplicaciones__anulada=False,
        aplicaciones__pago__anulada=False,
        aplicaciones__pago__estado__in=["pendiente", "confirmado"],
    )
    if asignaciones is not None:
        obligaciones = obligaciones.filter(asignacion__in=asignaciones)
    if obligaciones.exists():
        raise ValidationError(
            "No se puede modificar este registro mientras tenga pagos aplicados."
        )


def renovar_revisiones(compra, usuario):
    afectados = set(Asignacion.objects.filter(
        item__compra=compra, item__anulada=False, anulada=False
    ).values_list("beneficiario_id", flat=True))
    afectados.add(compra.pagador_id)
    anteriores = list(compra.revisiones.values("usuario_id", "estado"))
    compra.revisiones.exclude(usuario_id__in=afectados).delete()
    for usuario_id in afectados:
        RevisionCompra.objects.update_or_create(
            compra=compra, usuario_id=usuario_id, defaults={"estado": "pendiente"}
        )
    registrar_cambio(usuario, compra, "renovar_revisiones", {"antes": anteriores, "despues": "pendiente"})


def _datos_compra(compra):
    return {
        "fecha": compra.fecha.isoformat(),
        "pagador_id": compra.pagador_id,
        "total": str(compra.total),
        "impuesto": str(compra.impuesto),
        "descuento": str(compra.descuento),
        "descripcion": compra.descripcion,
    }


@transaction.atomic
def actualizar_compra(usuario, compra_id, *, fecha=None, total=None, descripcion=None, impuesto=None, descuento=None, pagador_id=None):
    grupo_id = Compra.objects.values_list("grupo_id", flat=True).get(pk=compra_id)
    Grupo.objects.select_for_update().get(pk=grupo_id)
    compra = Compra.objects.select_for_update().get(pk=compra_id)
    exigir_puede_editar_compra(compra, usuario)
    if compra.anulada:
        raise ValidationError("No se puede editar una compra anulada.")

    datos_anteriores = _datos_compra(compra)
    if fecha is not None:
        compra.fecha = fecha
    if descripcion is not None:
        if not isinstance(descripcion, str) or len(descripcion.strip()) > 150:
            raise ValidationError("La descripción de la compra no es válida.")
        compra.descripcion = descripcion.strip()
    if impuesto is not None or descuento is not None:
        try:
            nuevo_impuesto = Decimal(str(impuesto)) if impuesto is not None else compra.impuesto
            nuevo_descuento = Decimal(str(descuento)) if descuento is not None else compra.descuento
            for monto in (nuevo_impuesto, nuevo_descuento):
                if not monto.is_finite() or monto < 0 or monto > Decimal("9999999999.99") or monto != monto.quantize(Decimal("0.01")):
                    raise ValidationError("El IVA y el descuento deben ser valores válidos no negativos.")
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError("El IVA o el descuento no es válido.")
        subtotal = Item.objects.filter(compra=compra, anulada=False).aggregate(
            total=models.Sum("valor")
        )["total"] or Decimal("0.00")
        nuevo_total = subtotal + nuevo_impuesto - nuevo_descuento
        if nuevo_total <= 0 or nuevo_total > Decimal("9999999999.99"):
            raise ValidationError("El total resultante está fuera del rango permitido.")
        compra.impuesto = nuevo_impuesto
        compra.descuento = nuevo_descuento
        compra.total = nuevo_total
    if total is not None:
        try:
            nuevo_total = Decimal(str(total))
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError("El total indicado no es válido.")
        if not nuevo_total.is_finite() or nuevo_total <= 0 or nuevo_total > Decimal("9999999999.99") or nuevo_total != nuevo_total.quantize(Decimal("0.01")):
            raise ValidationError("El total debe ser positivo y tener máximo dos decimales.")
        if nuevo_total != compra.total:
            _exigir_sin_abonos(compra)
            subtotal = Item.objects.filter(compra=compra, anulada=False).aggregate(
                total=models.Sum("valor")
            )["total"] or Decimal("0.00")
            if nuevo_total != subtotal + compra.impuesto - compra.descuento:
                raise ValidationError("El total de la compra debe coincidir con sus ítems.")
            compra.total = nuevo_total

    if pagador_id is not None and pagador_id != compra.pagador_id:
        if pagador_id != compra.grupo.creador_id and not Membresia.objects.filter(grupo=compra.grupo, usuario_id=pagador_id, activo=True).exists():
            raise ValidationError("El pagador debe pertenecer al grupo.")
        compra.pagador_id = pagador_id

    datos_nuevos = _datos_compra(compra)
    if datos_anteriores != datos_nuevos:
        _exigir_sin_abonos(compra)
        compra.save()
        if datos_anteriores["pagador_id"] != datos_nuevos["pagador_id"]:
            for item in compra.items.filter(anulada=False):
                existentes = list(item.asignaciones.filter(anulada=False).select_related("beneficiario").order_by("beneficiario__first_name", "beneficiario__last_name", "beneficiario__email"))
                try:
                    valores = repartir(item.valor, [fila.beneficiario for fila in existentes], pagador=compra.pagador_id)
                except ValueError as error:
                    raise ValidationError(str(error))
                if any(valor <= 0 for valor in valores.values()):
                    raise ValidationError("El reparto debe asignar al menos un peso a cada integrante.")
                _reemplazar_asignaciones(item, usuario, valores, existentes)
        if datos_anteriores["pagador_id"] != datos_nuevos["pagador_id"] or datos_anteriores['impuesto'] != datos_nuevos['impuesto'] or datos_anteriores['descuento'] != datos_nuevos['descuento']:
            recalcular_ajustes_compra(compra.pk)
        renovar_revisiones(compra, usuario)
        registrar_cambio(
            usuario,
            compra,
            "editar",
            {"antes": datos_anteriores, "despues": datos_nuevos},
        )
    return compra


@transaction.atomic
def actualizar_item(usuario, item_id, *, valor, asignaciones, descripcion=None):
    grupo_id = Item.objects.values_list("compra__grupo_id", flat=True).get(pk=item_id)
    Grupo.objects.select_for_update().get(pk=grupo_id)
    item = Item.objects.select_for_update().select_related("compra").get(pk=item_id)
    exigir_puede_editar_compra(item.compra, usuario)
    if item.anulada or item.compra.anulada:
        raise ValidationError("No se puede editar un ítem anulado.")

    try:
        valor_nuevo = Decimal(str(valor))
        if not valor_nuevo.is_finite() or valor_nuevo <= 0 or valor_nuevo > Decimal("9999999999") or valor_nuevo != valor_nuevo.to_integral_value():
            raise ValidationError("El valor del ítem debe ser positivo y expresado en pesos enteros.")
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("El valor del ítem no es válido.")
    try:
        valores = {
            int(usuario_id): Decimal(str(monto))
            for usuario_id, monto in asignaciones.items()
        }
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        raise ValidationError("Las asignaciones indicadas no son válidas.")
    if not valores or any(
        not monto.is_finite() or monto <= 0 or monto > Decimal("9999999999.99") or monto != monto.quantize(Decimal("0.01"))
        for monto in valores.values()
    ):
        raise ValidationError("Cada asignación debe ser positiva y tener máximo dos decimales.")
    if sum(valores.values(), Decimal("0.00")) != valor_nuevo:
        raise ValidationError("La suma de las asignaciones debe coincidir con el valor del ítem.")

    compra = Compra.objects.select_for_update().get(pk=item.compra_id)
    existentes = list(Asignacion.objects.select_for_update().filter(item=item, anulada=False))
    _exigir_sin_abonos(compra)
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
    if compra.total <= 0 or compra.total > Decimal("9999999999.99"):
        raise ValidationError("El total de la compra está fuera del rango permitido.")
    compra.save(update_fields=["total"])
    item.valor = valor_nuevo
    if descripcion is not None:
        if not isinstance(descripcion, str) or not descripcion.strip() or len(descripcion.strip()) > 150:
            raise ValidationError("La descripción del ítem no es válida.")
        item.descripcion = descripcion.strip()
    item.save(update_fields=["valor", "descripcion"])
    _reemplazar_asignaciones(item, usuario, valores, existentes)
    recalcular_ajustes_compra(compra.pk)
    renovar_revisiones(compra, usuario)
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
    grupo_id = Item.objects.values_list("compra__grupo_id", flat=True).get(pk=item_id)
    Grupo.objects.select_for_update().get(pk=grupo_id)
    item = Item.objects.select_for_update().select_related("compra").get(pk=item_id)
    exigir_puede_editar_compra(item.compra, usuario)
    if item.anulada or item.compra.anulada:
        raise ValidationError("El ítem ya está anulado.")
    asignaciones = list(item.asignaciones.select_for_update().filter(anulada=False))
    _exigir_sin_abonos(item.compra)

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
    renovar_revisiones(compra, usuario)
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
    grupo_id = Compra.objects.values_list("grupo_id", flat=True).get(pk=compra_id)
    Grupo.objects.select_for_update().get(pk=grupo_id)
    compra = Compra.objects.select_for_update().get(pk=compra_id)
    exigir_puede_editar_compra(compra, usuario)
    if compra.anulada:
        raise ValidationError("La compra ya está anulada.")

    _exigir_sin_abonos(compra)
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


@transaction.atomic
def actualizar_items_compra(usuario, compra_id, cambios, *, fecha=None, descripcion=None, pagador_id=None, impuesto=None, descuento=None, version=None, nuevos=None):
    grupo_id = Compra.objects.values_list("grupo_id", flat=True).get(pk=compra_id)
    Grupo.objects.select_for_update().get(pk=grupo_id)
    compra = Compra.objects.select_for_update().get(pk=compra_id)
    exigir_puede_editar_compra(compra, usuario)
    if compra.anulada:
        raise ValidationError("La compra está anulada.")
    if version is not None and version != version_compra(compra):
        raise ValidationError("Otra persona modificó la compra. Vuelve a abrirla antes de guardar.")
    _exigir_sin_abonos(compra)
    items = {item.pk: item for item in compra.items.select_for_update().filter(anulada=False)}
    nuevos = nuevos or []
    if len(cambios) + len(nuevos) > 100 or set(cambios) != set(items):
        raise ValidationError("Los ítems no coinciden con la compra actual.")
    anterior = _datos_compra(compra)
    if pagador_id is not None:
        if pagador_id != compra.grupo.creador_id and not Membresia.objects.filter(grupo=compra.grupo, usuario_id=pagador_id, activo=True).exists():
            raise ValidationError("El pagador debe pertenecer al grupo.")
        compra.pagador_id = pagador_id
    if fecha is not None:
        compra.fecha = fecha
    if descripcion is not None:
        if not isinstance(descripcion, str) or len(descripcion.strip()) > 150:
            raise ValidationError("La descripción de la compra no es válida.")
        compra.descripcion = descripcion.strip()
    try:
        if impuesto is not None:
            compra.impuesto = Decimal(str(impuesto))
        if descuento is not None:
            compra.descuento = Decimal(str(descuento))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("El IVA o descuento no es válido.")
    for monto in (compra.impuesto, compra.descuento):
        if not monto.is_finite() or monto < 0 or monto > Decimal("9999999999.99") or monto != monto.quantize(Decimal("0.01")):
            raise ValidationError("El IVA o descuento no es válido.")
    preparados = []
    retirados = []
    subtotal = Decimal("0")
    for identificador, datos in list(cambios.items()) + [(None, datos) for datos in nuevos]:
        item = items.get(identificador)
        if item is not None and datos.get("retirar"):
            retirados.append(item)
            continue
        try:
            valor = Decimal(str(datos["valor"]))
        except (InvalidOperation, ValueError, TypeError, KeyError):
            raise ValidationError("El valor del ítem no es válido.")
        if not valor.is_finite() or valor <= 0 or valor > Decimal("9999999999") or valor != valor.to_integral_value():
            raise ValidationError("Cada ítem debe tener un valor positivo en pesos enteros.")
        try:
            valores = repartir(valor, datos["beneficiarios"], pagador=compra.pagador_id)
        except ValueError as error:
            raise ValidationError(str(error))
        if any(parte <= 0 for parte in valores.values()):
            raise ValidationError("Cada beneficiario debe recibir al menos un peso.")
        nombre_item = datos.get("descripcion", "")
        if not isinstance(nombre_item, str) or not nombre_item.strip() or len(nombre_item.strip()) > 150:
            raise ValidationError("Cada ítem debe tener una descripción.")
        preparados.append((item, nombre_item.strip(), valor, valores))
        subtotal += valor
    if not preparados:
        raise ValidationError("La compra debe conservar al menos un ítem.")
    total = subtotal + compra.impuesto - compra.descuento
    if total <= 0 or total > Decimal("9999999999.99"):
        raise ValidationError("El total resultante está fuera del rango permitido.")
    compra.total = total
    hubo_cambios = anterior != _datos_compra(compra)
    if hubo_cambios:
        compra.save()
    for item, descripcion, valor, valores in preparados:
        if item is None:
            item = Item.objects.create(compra=compra, descripcion=descripcion, valor=valor)
            _reemplazar_asignaciones(item, usuario, valores)
            registrar_cambio(usuario, item, "crear", {"despues": {"descripcion": descripcion, "valor": str(valor)}})
            hubo_cambios = True
            continue
        existentes = list(item.asignaciones.filter(anulada=False))
        anteriores = {fila.beneficiario_id: fila.valor_asignado for fila in existentes}
        if item.descripcion == descripcion and item.valor == valor and anteriores == valores and anterior['pagador_id'] == compra.pagador_id:
            continue
        hubo_cambios = True
        datos_anteriores = {"descripcion": item.descripcion, "valor": str(item.valor)}
        item.descripcion = descripcion
        item.valor = valor
        item.save(update_fields=["descripcion", "valor"])
        _reemplazar_asignaciones(item, usuario, valores, existentes)
        registrar_cambio(usuario, item, "editar", {"antes": datos_anteriores, "despues": {"descripcion": descripcion, "valor": str(valor)}})
    for item in retirados:
        ahora = timezone.now()
        item.anulada = True
        item.anulada_en = ahora
        item.anulada_por = usuario
        item.save(update_fields=["anulada", "anulada_en", "anulada_por"])
        for asignacion in item.asignaciones.filter(anulada=False):
            asignacion.anulada = True
            asignacion.anulada_en = ahora
            asignacion.anulada_por = usuario
            asignacion.save(update_fields=["anulada", "anulada_en", "anulada_por"])
        registrar_cambio(usuario, item, "anular", {"antes": {"descripcion": item.descripcion, "valor": str(item.valor)}, "despues": "anulado"})
        hubo_cambios = True
    if not hubo_cambios:
        return compra
    recalcular_ajustes_compra(compra.pk)
    renovar_revisiones(compra, usuario)
    registrar_cambio(usuario, compra, "editar_items", {"antes": anterior, "despues": _datos_compra(compra)})
    return compra


def version_compra(compra):
    from hashlib import sha256
    import json

    items = list(compra.items.filter(anulada=False).order_by("pk").values_list("pk", "descripcion", "valor"))
    asignaciones = list(Asignacion.objects.filter(item__compra=compra, item__anulada=False, anulada=False).order_by("pk").values_list("pk", "item_id", "beneficiario_id", "valor_asignado"))
    datos = [_datos_compra(compra), compra.anulada, items, asignaciones]
    return sha256(json.dumps(datos, default=str, sort_keys=True).encode()).hexdigest()

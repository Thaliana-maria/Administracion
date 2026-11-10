from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from auditlog.services import registrar_cambio
from expenses.services.permisos import (
    es_administrador,
    exigir_miembro,
    exigir_puede_editar_pago,
)
from ledger.models import AplicacionPago, Obligacion, Pago


def _normalizar_aplicaciones(aplicaciones):
    normalizadas = []
    for obligacion_id, monto in aplicaciones:
        valor = Decimal(str(monto))
        if valor <= 0 or valor != valor.quantize(Decimal("0.01")):
            raise ValidationError("Cada abono debe ser positivo y tener máximo dos decimales.")
        normalizadas.append((int(obligacion_id), valor))
    if len({obligacion_id for obligacion_id, _ in normalizadas}) != len(normalizadas):
        raise ValidationError("Una obligación no puede repetirse en el mismo pago.")
    return normalizadas


def _validar_aplicaciones(
    *,
    grupo_id,
    deudor_id,
    acreedor_id,
    monto,
    aplicaciones,
    excluir_pago_id=None,
):
    normalizadas = _normalizar_aplicaciones(aplicaciones)
    if not normalizadas:
        raise ValidationError("El pago debe aplicarse a una o más obligaciones.")
    if sum((valor for _, valor in normalizadas), Decimal("0.00")) != monto:
        raise ValidationError("La suma de los abonos debe coincidir con el monto del pago.")

    aplicaciones_validadas = []
    for obligacion_id, valor in normalizadas:
        obligacion = (
            Obligacion.objects.select_for_update()
            .select_related("asignacion__item__compra")
            .get(pk=obligacion_id)
        )
        if (
            obligacion.grupo_id != grupo_id
            or obligacion.deudor_id != deudor_id
            or obligacion.acreedor_id != acreedor_id
            or obligacion.anulada
            or obligacion.asignacion.anulada
            or obligacion.asignacion.item.anulada
            or obligacion.asignacion.item.compra.anulada
        ):
            raise ValidationError("El abono no corresponde a una obligación activa de este pago.")

        pagos_aplicados = AplicacionPago.objects.filter(
            obligacion=obligacion,
            anulada=False,
            pago__anulada=False,
        )
        if excluir_pago_id is not None:
            pagos_aplicados = pagos_aplicados.exclude(pago_id=excluir_pago_id)
        monto_aplicado = pagos_aplicados.aggregate(total=Sum("monto"))["total"] or Decimal("0.00")
        if monto_aplicado + valor > obligacion.monto:
            raise ValidationError("El abono supera el saldo pendiente de la obligación.")
        aplicaciones_validadas.append((obligacion, valor))
    return aplicaciones_validadas


def _registrar_aplicaciones(pago, aplicaciones):
    creadas = []
    for obligacion, monto in aplicaciones:
        creadas.append(
            AplicacionPago.objects.create(
                pago=pago,
                obligacion=obligacion,
                monto=monto,
            )
        )
    return creadas


@transaction.atomic
def registrar_pago(
    usuario,
    *,
    grupo_id,
    deudor_id,
    acreedor_id,
    monto,
    fecha,
    aplicaciones,
):
    exigir_miembro(grupo_id, usuario)
    if not es_administrador(grupo_id, usuario) and usuario.pk != deudor_id:
        raise PermissionDenied("Un miembro solo puede registrar sus propios pagos.")

    monto = Decimal(str(monto))
    if monto <= 0 or monto != monto.quantize(Decimal("0.01")):
        raise ValidationError("El monto debe ser positivo y tener máximo dos decimales.")
    aplicaciones_validadas = _validar_aplicaciones(
        grupo_id=grupo_id,
        deudor_id=deudor_id,
        acreedor_id=acreedor_id,
        monto=monto,
        aplicaciones=aplicaciones,
    )
    pago = Pago.objects.create(
        grupo_id=grupo_id,
        deudor_id=deudor_id,
        acreedor_id=acreedor_id,
        monto=monto,
        fecha=fecha,
        registrado_por=usuario,
    )
    _registrar_aplicaciones(pago, aplicaciones_validadas)
    registrar_cambio(
        usuario,
        pago,
        "registrar",
        {
            "monto": str(monto),
            "deudor_id": deudor_id,
            "acreedor_id": acreedor_id,
            "obligaciones": [
                {"obligacion_id": obligacion.pk, "monto": str(valor)}
                for obligacion, valor in aplicaciones_validadas
            ],
        },
    )
    return pago


@transaction.atomic
def actualizar_pago(
    usuario,
    pago_id,
    *,
    monto,
    fecha,
    aplicaciones,
    deudor_id=None,
    acreedor_id=None,
):
    pago = Pago.objects.select_for_update().get(pk=pago_id)
    exigir_puede_editar_pago(pago, usuario)
    if pago.anulada:
        raise ValidationError("No se puede editar un pago anulado.")

    monto = Decimal(str(monto))
    if monto <= 0 or monto != monto.quantize(Decimal("0.01")):
        raise ValidationError("El monto debe ser positivo y tener máximo dos decimales.")
    deudor_id = pago.deudor_id if deudor_id is None else int(deudor_id)
    acreedor_id = pago.acreedor_id if acreedor_id is None else int(acreedor_id)
    if deudor_id == acreedor_id:
        raise ValidationError("El deudor y el acreedor deben ser personas distintas.")
    if not es_administrador(pago.grupo_id, usuario) and (
        deudor_id != pago.deudor_id or acreedor_id != pago.acreedor_id
    ):
        raise PermissionDenied("Solo un administrador puede corregir las partes del pago.")
    aplicaciones_existentes = pago.aplicaciones.filter(anulada=False).exists()
    aplicaciones_validadas = (
        _validar_aplicaciones(
            grupo_id=pago.grupo_id,
            deudor_id=deudor_id,
            acreedor_id=acreedor_id,
            monto=monto,
            aplicaciones=aplicaciones,
            excluir_pago_id=pago.pk,
        )
        if aplicaciones_existentes or aplicaciones
        else []
    )
    aplicaciones_anteriores = list(
        pago.aplicaciones.filter(anulada=False).values(
            "obligacion_id", "monto"
        )
    )
    datos_anteriores = {
        "monto": str(pago.monto),
        "fecha": pago.fecha.isoformat(),
        "deudor_id": pago.deudor_id,
        "acreedor_id": pago.acreedor_id,
    }
    pago.monto = monto
    pago.fecha = fecha
    pago.deudor_id = deudor_id
    pago.acreedor_id = acreedor_id
    pago.save(update_fields=["monto", "fecha", "deudor", "acreedor"])

    ahora = timezone.now()
    pago.aplicaciones.filter(anulada=False).update(anulada=True)
    _registrar_aplicaciones(pago, aplicaciones_validadas)
    registrar_cambio(
        usuario,
        pago,
        "editar",
        {
            "antes": datos_anteriores,
            "despues": {
                "monto": str(pago.monto),
                "fecha": pago.fecha.isoformat(),
                "deudor_id": pago.deudor_id,
                "acreedor_id": pago.acreedor_id,
            },
            "aplicaciones_anteriores": [
                {"obligacion_id": row["obligacion_id"], "monto": str(row["monto"])}
                for row in aplicaciones_anteriores
            ],
            "aplicaciones_nuevas": [
                {"obligacion_id": obligacion.pk, "monto": str(valor)}
                for obligacion, valor in aplicaciones_validadas
            ],
            "editado_en": ahora.isoformat(),
        },
    )
    return pago


@transaction.atomic
def anular_pago(usuario, pago_id):
    pago = Pago.objects.select_for_update().get(pk=pago_id)
    exigir_puede_editar_pago(pago, usuario)
    if pago.anulada:
        raise ValidationError("El pago ya está anulado.")

    detalles = {
        "monto": str(pago.monto),
        "deudor_id": pago.deudor_id,
        "acreedor_id": pago.acreedor_id,
        "aplicaciones": [
            {"obligacion_id": row.obligacion_id, "monto": str(row.monto)}
            for row in pago.aplicaciones.filter(anulada=False)
        ],
    }
    pago.anulada = True
    pago.anulada_en = timezone.now()
    pago.anulada_por = usuario
    pago.save(update_fields=["anulada", "anulada_en", "anulada_por"])
    registrar_cambio(usuario, pago, "anular", detalles)
    return pago

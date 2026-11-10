from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from expenses.models import AjusteCompra, Asignacion, Compra
from ledger.models import Obligacion


def _distribuir_ajuste(compra, asignaciones):
    ajuste_total = compra.impuesto - compra.descuento
    centavos = int(ajuste_total * 100)
    if centavos == 0:
        return {usuario_id: Decimal("0.00") for usuario_id, _, _ in asignaciones}

    totales = {}
    nombres = {}
    for usuario_id, nombre, valor in asignaciones:
        totales[usuario_id] = totales.get(usuario_id, Decimal("0.00")) + valor
        nombres[usuario_id] = nombre
    base_total = sum(totales.values(), Decimal("0.00"))
    if base_total <= 0:
        raise ValidationError("No se puede distribuir IVA o descuento sin asignaciones activas.")

    signo = 1 if centavos > 0 else -1
    magnitud = abs(centavos)
    base_centavos = {usuario_id: int(valor * 100) for usuario_id, valor in totales.items()}
    cuotas = {
        usuario_id: (magnitud * valor) // int(base_total * 100)
        for usuario_id, valor in base_centavos.items()
    }
    restante = magnitud - sum(cuotas.values())
    orden = sorted(
        totales,
        key=lambda usuario_id: (
            -((magnitud * base_centavos[usuario_id]) % int(base_total * 100)),
            nombres[usuario_id].casefold(),
            usuario_id,
        ),
    )
    for usuario_id in orden[:restante]:
        cuotas[usuario_id] += 1

    resultado = {
        usuario_id: Decimal(signo * cuota) / Decimal("100")
        for usuario_id, cuota in cuotas.items()
    }
    if any(totales[usuario_id] + resultado[usuario_id] < 0 for usuario_id in totales):
        raise ValidationError("El descuento supera el gasto asignado a uno de los integrantes.")
    return resultado


@transaction.atomic
def recalcular_ajustes_compra(compra_id):
    compra = Compra.objects.select_for_update().get(pk=compra_id)
    asignaciones = list(
        Asignacion.objects.filter(
            item__compra=compra,
            item__anulada=False,
            anulada=False,
        )
        .select_related("beneficiario")
        .order_by("beneficiario__first_name", "beneficiario__last_name", "beneficiario_id", "pk")
        .values_list(
            "beneficiario_id",
            "beneficiario__first_name",
            "beneficiario__last_name",
            "valor_asignado",
            "pk",
        )
    )
    agrupadas = []
    por_integrante = {}
    for usuario_id, nombre, apellido, valor, asignacion_id in asignaciones:
        nombre_completo = f"{nombre} {apellido}".strip()
        agrupadas.append((usuario_id, nombre_completo, valor))
        por_integrante.setdefault(usuario_id, []).append((asignacion_id, valor))

    ajustes = _distribuir_ajuste(compra, agrupadas)
    activos = set(ajustes)
    AjusteCompra.objects.filter(compra=compra).exclude(
        beneficiario_id__in=activos
    ).update(monto=Decimal("0.00"))
    for usuario_id, monto in ajustes.items():
        AjusteCompra.objects.update_or_create(
            compra=compra,
            beneficiario_id=usuario_id,
            defaults={"monto": monto},
        )

    obligaciones = Obligacion.objects.filter(asignacion__item__compra=compra)
    for usuario_id, filas in por_integrante.items():
        deudor_obligaciones = list(
            obligaciones.filter(
                deudor_id=usuario_id,
                anulada=False,
                asignacion__anulada=False,
                asignacion__item__anulada=False,
            ).select_related("asignacion").order_by("asignacion_id")
        )
        if not deudor_obligaciones:
            continue
        ajuste_centavos = int(ajustes.get(usuario_id, Decimal("0.00")) * 100)
        total_centavos = sum(
            int(obligacion.asignacion.valor_asignado * 100)
            for obligacion in deudor_obligaciones
        )
        magnitud = abs(ajuste_centavos)
        signo = 1 if ajuste_centavos > 0 else -1
        cuotas = {
            obligacion.pk: (
                magnitud * int(obligacion.asignacion.valor_asignado * 100)
            )
            // total_centavos
            for obligacion in deudor_obligaciones
        }
        restante = magnitud - sum(cuotas.values())
        orden = sorted(
            deudor_obligaciones,
            key=lambda obligacion: (
                -(
                    magnitud * int(obligacion.asignacion.valor_asignado * 100)
                    % total_centavos
                ),
                obligacion.asignacion_id,
            ),
        )
        for obligacion in orden[:restante]:
            cuotas[obligacion.pk] += 1

        for obligacion in deudor_obligaciones:
            parte = Decimal(signo * cuotas[obligacion.pk]) / Decimal("100")
            monto_nuevo = obligacion.asignacion.valor_asignado + parte
            if monto_nuevo <= 0:
                raise ValidationError("El descuento no puede eliminar una deuda existente.")
            if obligacion.monto != monto_nuevo:
                if obligacion.aplicaciones.filter(
                    anulada=False, pago__anulada=False
                ).exists():
                    raise ValidationError(
                        "No se puede cambiar IVA, descuento o asignaciones "
                        "mientras haya abonos aplicados."
                    )
                obligacion.monto = monto_nuevo
                obligacion.save(update_fields=["monto"])
            restante -= parte

    return ajustes

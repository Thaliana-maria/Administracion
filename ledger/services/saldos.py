from decimal import Decimal
from django.db.models import Sum
from expenses.models import Membresia, Compra, Asignacion
from ledger.models import Pago


def calcular_saldos(grupo):
    """Calcula el saldo de cada integrante usando consultas agrupadas.

    Saldo = compras pagadas - gastos asignados + pagos enviados - pagos recibidos.
    Un saldo positivo significa que le deben dinero; uno negativo significa que debe.
    """
    grupo_id = grupo.id if hasattr(grupo, "id") else grupo
    miembros = Membresia.objects.filter(grupo_id=grupo_id).values_list("usuario_id", flat=True)
    saldos = {usuario_id: Decimal("0.00") for usuario_id in miembros}

                                                               
    compras = Compra.objects.filter(grupo_id=grupo_id).values("pagador_id").annotate(
        total=Sum("total")
    )
    for movimiento in compras:
        if movimiento["pagador_id"] in saldos:
            saldos[movimiento["pagador_id"]] += movimiento["total"] or Decimal("0.00")

    asignaciones = Asignacion.objects.filter(
        item__compra__grupo_id=grupo_id
    ).values("beneficiario_id").annotate(total=Sum("valor_asignado"))
    for movimiento in asignaciones:
        if movimiento["beneficiario_id"] in saldos:
            saldos[movimiento["beneficiario_id"]] -= movimiento["total"] or Decimal("0.00")

    pagos_enviados = Pago.objects.filter(grupo_id=grupo_id).values("deudor_id").annotate(
        total=Sum("monto")
    )
    for movimiento in pagos_enviados:
        if movimiento["deudor_id"] in saldos:
            saldos[movimiento["deudor_id"]] += movimiento["total"] or Decimal("0.00")

    pagos_recibidos = Pago.objects.filter(grupo_id=grupo_id).values("acreedor_id").annotate(
        total=Sum("monto")
    )
    for movimiento in pagos_recibidos:
        if movimiento["acreedor_id"] in saldos:
            saldos[movimiento["acreedor_id"]] -= movimiento["total"] or Decimal("0.00")

    return saldos

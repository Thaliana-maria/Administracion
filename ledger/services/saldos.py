from decimal import Decimal
from django.db.models import Sum
from expenses.models import AjusteCompra, Grupo, Membresia, Compra, Asignacion
from ledger.models import Pago, Compensacion


def calcular_saldos(grupo):
    """Calcula el saldo de cada integrante usando consultas agrupadas.

    Saldo = compras pagadas - gastos asignados + pagos enviados - pagos recibidos.
    Un saldo positivo significa que le deben dinero; uno negativo significa que debe.
    """
    grupo_id = grupo.id if hasattr(grupo, "id") else grupo
    miembros = Membresia.objects.filter(
        grupo_id=grupo_id, activo=True
    ).values_list("usuario_id", flat=True).union(
        Grupo.objects.filter(pk=grupo_id).values_list("creador_id", flat=True)
    )
    saldos = {usuario_id: Decimal("0.00") for usuario_id in miembros}

    compras = Compra.objects.filter(grupo_id=grupo_id, anulada=False).values("pagador_id").annotate(
        total=Sum("total")
    )
    for movimiento in compras:
        usuario_id = movimiento["pagador_id"]
        saldos[usuario_id] = saldos.get(usuario_id, Decimal("0.00")) + (movimiento["total"] or Decimal("0.00"))

    asignaciones = Asignacion.objects.filter(
        item__compra__grupo_id=grupo_id,
        item__compra__anulada=False,
        item__anulada=False,
        anulada=False,
    ).values("beneficiario_id").annotate(total=Sum("valor_asignado"))
    for movimiento in asignaciones:
        usuario_id = movimiento["beneficiario_id"]
        saldos[usuario_id] = saldos.get(usuario_id, Decimal("0.00")) - (movimiento["total"] or Decimal("0.00"))

    ajustes = AjusteCompra.objects.filter(
        compra__grupo_id=grupo_id,
        compra__anulada=False,
    ).values("beneficiario_id").annotate(total=Sum("monto"))
    for movimiento in ajustes:
        usuario_id = movimiento["beneficiario_id"]
        saldos[usuario_id] = saldos.get(usuario_id, Decimal("0.00")) - (movimiento["total"] or Decimal("0.00"))

    pagos_enviados = Pago.objects.filter(grupo_id=grupo_id, anulada=False, estado="confirmado").values("deudor_id").annotate(
        total=Sum("monto")
    )
    for movimiento in pagos_enviados:
        usuario_id = movimiento["deudor_id"]
        saldos[usuario_id] = saldos.get(usuario_id, Decimal("0.00")) + (movimiento["total"] or Decimal("0.00"))

    pagos_recibidos = Pago.objects.filter(grupo_id=grupo_id, anulada=False, estado="confirmado").values("acreedor_id").annotate(
        total=Sum("monto")
    )
    for movimiento in pagos_recibidos:
        usuario_id = movimiento["acreedor_id"]
        saldos[usuario_id] = saldos.get(usuario_id, Decimal("0.00")) - (movimiento["total"] or Decimal("0.00"))

    compensaciones = Compensacion.objects.filter(grupo_id=grupo_id, estado="aplicada")
    for movimiento in compensaciones.values("deudor_id").annotate(total=Sum("monto")):
        persona = movimiento["deudor_id"]
        saldos[persona] = saldos.get(persona, Decimal("0.00")) + movimiento["total"]
    for movimiento in compensaciones.values("acreedor_id").annotate(total=Sum("monto")):
        persona = movimiento["acreedor_id"]
        saldos[persona] = saldos.get(persona, Decimal("0.00")) - movimiento["total"]

    return saldos

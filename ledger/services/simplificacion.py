from decimal import Decimal
from functools import lru_cache

from ledger.services.saldos import calcular_saldos
from django.db.models import Q, Sum
from ledger.models import Obligacion


def simplificar_deudas(grupo, *, saldos=None):
    """Calcula transferencias sugeridas; para grupos grandes utiliza una aproximación."""
    if saldos is None:
        saldos = calcular_saldos(grupo)
    centavos = tuple(
        (usuario_id, int(saldo * 100))
        for usuario_id, saldo in sorted(saldos.items())
        if saldo
    )
    if sum(saldo for _, saldo in centavos) != 0:
        raise ValueError("Los saldos del grupo no están balanceados.")

    @lru_cache(maxsize=None)
    def resolver(estado):
        if not estado:
            return ()

        usuario_id, saldo = estado[0]
        mejor = None
        vistos = set()
        for indice in range(1, len(estado)):
            otro_id, otro_saldo = estado[indice]
            if (saldo > 0) == (otro_saldo > 0) or otro_saldo in vistos:
                continue
            vistos.add(otro_saldo)

            monto = min(abs(saldo), abs(otro_saldo))
            siguiente = []
            restante_usuario = saldo - (monto if saldo > 0 else -monto)
            restante_otro = otro_saldo - (monto if otro_saldo > 0 else -monto)
            if restante_usuario:
                siguiente.append((usuario_id, restante_usuario))
            if restante_otro:
                siguiente.append((otro_id, restante_otro))
            siguiente.extend(estado[1:indice])
            siguiente.extend(estado[indice + 1 :])
            siguiente = tuple(sorted(siguiente))

            subplan = resolver(siguiente)
            if saldo < 0:
                transferencia = (usuario_id, otro_id, monto)
            else:
                transferencia = (otro_id, usuario_id, monto)
            candidato = (transferencia,) + subplan
            if mejor is None or (len(candidato), candidato) < (len(mejor), mejor):
                mejor = candidato

            if restante_usuario == 0 and restante_otro == 0:
                break
        return mejor or ()

    if len(centavos) > 10:
        deudores = [[usuario, -saldo] for usuario, saldo in centavos if saldo < 0]
        acreedores = [[usuario, saldo] for usuario, saldo in centavos if saldo > 0]
        plan = []
        i = j = 0
        while i < len(deudores) and j < len(acreedores):
            monto = min(deudores[i][1], acreedores[j][1])
            plan.append((deudores[i][0], acreedores[j][0], monto))
            deudores[i][1] -= monto
            acreedores[j][1] -= monto
            if not deudores[i][1]:
                i += 1
            if not acreedores[j][1]:
                j += 1
    else:
        plan = resolver(centavos)

    return [
        {
            "deudor_id": deudor_id,
            "acreedor_id": acreedor_id,
            "monto": Decimal(monto_centavos) / Decimal("100"),
        }
        for deudor_id, acreedor_id, monto_centavos in plan
    ]


def transferencias_disponibles(grupo):
    obligaciones = Obligacion.objects.filter(
        grupo=grupo, anulada=False, asignacion__anulada=False,
        asignacion__item__anulada=False, asignacion__item__compra__anulada=False,
    ).exclude(asignacion__item__compra__revisiones__estado="objetada").annotate(
        reservado=Sum("aplicaciones__monto", filter=Q(
            aplicaciones__anulada=False, aplicaciones__pago__anulada=False,
            aplicaciones__pago__estado__in=["pendiente", "confirmado"]
        ))
    )
    montos = {}
    for deudor_id, acreedor_id, monto, reservado in obligaciones.values_list("deudor_id", "acreedor_id", "monto", "reservado").iterator():
        pendiente = monto - (reservado or Decimal("0"))
        if pendiente > 0:
            clave = (deudor_id, acreedor_id)
            montos[clave] = montos.get(clave, Decimal("0")) + pendiente
    return [{"deudor_id": deudor, "acreedor_id": acreedor, "monto": monto}
            for (deudor, acreedor), monto in sorted(montos.items())]

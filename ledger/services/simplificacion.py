from decimal import Decimal
from functools import lru_cache

from ledger.services.saldos import calcular_saldos


def simplificar_deudas(grupo):
    """Calcula una liquidación con el menor número de transferencias."""
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

    return [
        {
            "deudor_id": deudor_id,
            "acreedor_id": acreedor_id,
            "monto": Decimal(monto_centavos) / Decimal("100"),
        }
        for deudor_id, acreedor_id, monto_centavos in resolver(centavos)
    ]

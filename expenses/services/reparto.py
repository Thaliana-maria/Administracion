from decimal import Decimal


def repartir(valor, beneficiarios, pagador=None):
    """Divide un valor entre beneficiarios aplicando la regla RN-05.

    Cada parte se trunca a pesos enteros. Los pesos que sobran se entregan
    primero al pagador (si está en la lista) y luego por orden alfabetico.
    El resultado es un diccionario con el id de cada persona y su parte.
    """
    valor = Decimal(str(valor))
    if valor <= 0:
        raise ValueError("El valor debe ser mayor que cero")
    if valor != valor.to_integral_value():
        raise ValueError("Para RN-05 el valor debe estar expresado en pesos enteros")
    if not beneficiarios:
        raise ValueError("Debe haber por lo menos un beneficiario")

    personas = []
    for persona in beneficiarios:
        if isinstance(persona, dict):
            identificador = persona["id"]
            nombre = persona["nombre"]
        else:
            identificador = persona.id
            nombre = persona.get_full_name() or str(persona)
        personas.append((identificador, nombre))

    if len({persona[0] for persona in personas}) != len(personas):
        raise ValueError("No debe haber beneficiarios repetidos")

    parte = int(valor) // len(personas)
    sobrante = int(valor) - (parte * len(personas))
    resultado = {identificador: Decimal(parte) for identificador, nombre in personas}

    orden = sorted(personas, key=lambda persona: persona[1].lower())
    if pagador is not None:
        orden = sorted(orden, key=lambda persona: persona[0] != pagador)

    for identificador, nombre in orden[:sobrante]:
        resultado[identificador] += Decimal("1")

    return resultado

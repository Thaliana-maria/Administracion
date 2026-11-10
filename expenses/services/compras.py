from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from auditlog.services import registrar_cambio
from expenses.models import Asignacion, Compra, Grupo, Item, Membresia
from expenses.services.ajustes import recalcular_ajustes_compra
from expenses.services.permisos import exigir_miembro
from expenses.services.reparto import repartir

Usuario = get_user_model()


def _validar_monto(valor, etiqueta, *, permitir_cero=False):
    try:
        monto = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValidationError(f"{etiqueta} debe ser un valor monetario válido.") from error
    if not monto.is_finite() or monto < 0 or (monto == 0 and not permitir_cero):
        raise ValidationError(f"{etiqueta} debe ser mayor que cero.")
    if monto >= Decimal("10000000000"):
        raise ValidationError(f"{etiqueta} supera el máximo permitido.")
    if monto != monto.quantize(Decimal("0.01")):
        raise ValidationError(f"{etiqueta} admite máximo dos decimales.")
    return monto


@transaction.atomic
def crear_compra(
    usuario,
    grupo_id,
    *,
    fecha,
    pagador_id,
    descripcion="",
    impuesto=0,
    descuento=0,
    total_declarado,
    items,
):
    grupo = Grupo.objects.get(pk=grupo_id)
    exigir_miembro(grupo, usuario)
    integrantes = set(
        Membresia.objects.filter(grupo=grupo, activo=True).values_list(
            "usuario_id", flat=True
        )
    )
    integrantes.add(grupo.creador_id)
    pagador_id = int(pagador_id)
    if pagador_id not in integrantes:
        raise ValidationError("El pagador debe ser un integrante activo del grupo.")

    impuesto = _validar_monto(impuesto, "El IVA", permitir_cero=True)
    descuento = _validar_monto(descuento, "El descuento", permitir_cero=True)
    total_declarado = _validar_monto(total_declarado, "El total")
    filas = [fila for fila in items if fila]
    if not filas:
        raise ValidationError("Agrega al menos un ítem.")

    lineas = []
    for numero, fila in enumerate(filas, start=1):
        valor = _validar_monto(fila["valor"], f"El valor del ítem {numero}")
        if valor != valor.to_integral_value():
            raise ValidationError(
                f"El ítem {numero} debe estar expresado en pesos enteros según RN-05."
            )
        beneficiarios = {int(persona_id) for persona_id in fila["beneficiarios"]}
        if not beneficiarios:
            raise ValidationError(f"Selecciona beneficiarios para el ítem {numero}.")
        if not beneficiarios.issubset(integrantes):
            raise ValidationError(
                f"Todos los beneficiarios del ítem {numero} deben ser integrantes activos."
            )
        lineas.append(
            {
                "descripcion": fila["descripcion"].strip(),
                "valor": valor,
                "beneficiarios": beneficiarios,
            }
        )

    subtotal = sum((linea["valor"] for linea in lineas), Decimal("0.00"))
    total_calculado = subtotal + impuesto - descuento
    if total_calculado <= 0:
        raise ValidationError("El total de la compra debe ser mayor que cero.")
    if total_declarado != total_calculado:
        diferencia = total_declarado - total_calculado
        raise ValidationError(
            f"Total declarado ${total_declarado:.2f}; el total correcto es "
            f"${total_calculado:.2f} (diferencia ${diferencia:.2f})."
        )

    compra = Compra.objects.create(
        grupo=grupo,
        pagador_id=pagador_id,
        registrado_por=usuario,
        fecha=fecha,
        total=total_calculado,
        impuesto=impuesto,
        descuento=descuento,
        descripcion=descripcion.strip(),
    )
    for linea in lineas:
        item = Item.objects.create(
            compra=compra,
            descripcion=linea["descripcion"],
            valor=linea["valor"],
        )
        usuarios = list(
            Usuario.objects.filter(pk__in=linea["beneficiarios"]).order_by(
                "first_name", "last_name", "email"
            )
        )
        reparto = repartir(linea["valor"], usuarios, pagador=pagador_id)
        for beneficiario_id, monto in reparto.items():
            Asignacion.objects.create(
                item=item,
                beneficiario_id=beneficiario_id,
                valor_asignado=monto,
            )

    recalcular_ajustes_compra(compra.pk)
    registrar_cambio(
        usuario,
        compra,
        "crear",
        {
            "total": str(compra.total),
            "subtotal_items": str(subtotal),
            "impuesto": str(impuesto),
            "descuento": str(descuento),
        },
    )
    return compra

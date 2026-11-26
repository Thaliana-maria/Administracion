
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from auditlog.models import Historial
from expenses.models import (
    Asignacion,
    Compra,
    Grupo,
    Item,
    Membresia,
)
from expenses.services.permisos import (
    es_administrador,
    es_miembro,
)
from expenses.services.reparto import repartir


DESTINOS = ("todos", "persona", "mascota")


@transaction.atomic
def registrar_grupo(creador, nombre):
    """Crea un grupo y registra al creador como su primer administrador."""
    nombre = (nombre or "").strip()

    if not nombre:
        raise ValidationError("El nombre del grupo es obligatorio.")

    grupo = Grupo.objects.create(
        nombre=nombre,
        creador=creador,
    )

    Membresia.objects.create(
        grupo=grupo,
        usuario=creador,
        rol=Membresia.Rol.ADMINISTRADOR,
        activo=True,
    )

    Historial.objects.create(
        usuario=creador,
        tipo_registro="Grupo",
        id_registro=grupo.pk,
        accion="crear",
    )

    return grupo


@transaction.atomic
def agregar_integrante(grupo, usuario, quien_agrega):
    """
    Agrega o reactiva un integrante.

    Únicamente los administradores del grupo pueden realizar esta acción.
    Una membresía reactivada vuelve al rol de miembro.
    """
    grupo_bloqueado = Grupo.objects.select_for_update().filter(
        pk=grupo.pk
    ).first()

    if grupo_bloqueado is None:
        raise ValidationError("El grupo indicado no existe.")

    if not es_administrador(grupo_bloqueado, quien_agrega):
        raise ValidationError(
            "Solo los administradores del grupo pueden agregar integrantes."
        )

    if usuario.pk == grupo_bloqueado.creador_id:
        raise ValidationError("El creador ya pertenece al grupo.")

    membresia = Membresia.objects.select_for_update().filter(
        grupo=grupo_bloqueado,
        usuario=usuario,
    ).first()

    if membresia is not None and membresia.activo:
        raise ValidationError("Esa persona ya es integrante del grupo.")

    if membresia is not None:
        membresia.activo = True
        membresia.rol = Membresia.Rol.MIEMBRO
        membresia.save(update_fields=["activo", "rol"])
        accion = "reactivar"
    else:
        membresia = Membresia.objects.create(
            grupo=grupo_bloqueado,
            usuario=usuario,
            rol=Membresia.Rol.MIEMBRO,
            activo=True,
        )
        accion = "crear"

    Historial.objects.create(
        usuario=quien_agrega,
        tipo_registro="Membresia",
        id_registro=membresia.pk,
        accion=accion,
    )

    return membresia


def _valor_entero_positivo(bruto, posicion):
    try:
        valor = Decimal(str(bruto))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError(
            f"Ítem {posicion}: el valor no es un número válido."
        )

    if not valor.is_finite():
        raise ValidationError(
            f"Ítem {posicion}: el valor debe ser un número válido."
        )

    if valor <= 0:
        raise ValidationError(
            f"Ítem {posicion}: el valor debe ser mayor que cero."
        )

    if valor > Decimal("9999999999"):
        raise ValidationError(f"Ítem {posicion}: el valor supera el máximo permitido.")

    if valor != valor.to_integral_value():
        raise ValidationError(
            f"Ítem {posicion}: el valor debe estar en pesos enteros."
        )

    return valor


def validar_items(grupo, items):
    """
    Valida y normaliza los ítems.

    Solo incluye integrantes activos y al creador del grupo.
    """
    if not items:
        raise ValidationError(
            "La compra debe tener por lo menos un ítem."
        )

    membresias = Membresia.objects.filter(
        grupo=grupo,
        activo=True,
    ).select_related("usuario")

    miembros_por_id = {
        membresia.usuario_id: membresia.usuario
        for membresia in membresias
    }

    # El creador siempre forma parte del grupo.
    miembros_por_id[grupo.creador_id] = grupo.creador

    miembros = list(miembros_por_id.values())
    normalizados = []

    for posicion, item in enumerate(items, start=1):
        descripcion = (item.get("descripcion") or "").strip()

        if not descripcion:
            raise ValidationError(
                f"Ítem {posicion}: la descripción es obligatoria."
            )

        valor = _valor_entero_positivo(
            item.get("valor"),
            posicion,
        )

        destino = item.get("destino") or "todos"

        if destino not in DESTINOS:
            raise ValidationError(
                f"Ítem {posicion}: el destino «{destino}» no es válido."
            )

        beneficiario = None

        if destino == "persona":
            bruto = item.get("beneficiario")
            beneficiario_id = getattr(bruto, "pk", bruto)

            if beneficiario_id in (None, ""):
                raise ValidationError(
                    f"Ítem {posicion}: debe elegir a quién se le asigna."
                )

            try:
                beneficiario_id = int(beneficiario_id)
            except (TypeError, ValueError):
                raise ValidationError(
                    f"Ítem {posicion}: el beneficiario indicado no es válido."
                )

            beneficiario = miembros_por_id.get(beneficiario_id)

            if beneficiario is None:
                raise ValidationError(
                    f"Ítem {posicion}: la persona asignada no pertenece "
                    "al grupo o está inactiva."
                )

        normalizados.append({
            "descripcion": descripcion,
            "valor": valor,
            "destino": destino,
            "beneficiario": beneficiario,
        })

    return normalizados, miembros


@transaction.atomic
def registrar_compra(
    grupo,
    pagador,
    fecha,
    descripcion,
    items,
    registrado_por=None,
):
    """
    Registra una compra con sus ítems y asignaciones.

    Los destinos 'todos' y 'mascota' se reparten entre integrantes activos.
    El destino 'persona' asigna el importe completo a una persona activa.
    """
    grupo_bloqueado = Grupo.objects.select_for_update().filter(
        pk=grupo.pk
    ).first()

    if grupo_bloqueado is None:
        raise ValidationError("El grupo indicado no existe.")

    registrado_por = registrado_por or pagador

    if not es_miembro(grupo_bloqueado, registrado_por):
        raise ValidationError(
            "Solo los integrantes activos del grupo pueden registrar compras."
        )

    if not es_miembro(grupo_bloqueado, pagador):
        raise ValidationError(
            "El pagador debe ser integrante activo del grupo."
        )

    normalizados, miembros = validar_items(
        grupo_bloqueado,
        items,
    )

    ids_activos = {miembro.pk for miembro in miembros}

    if pagador.pk not in ids_activos:
        raise ValidationError(
            "El pagador debe ser integrante activo del grupo."
        )

    if registrado_por.pk not in ids_activos:
        raise ValidationError(
            "Quien registra la compra debe ser integrante activo del grupo."
        )

    total = sum(
        (item["valor"] for item in normalizados),
        Decimal("0"),
    )

    if total > Decimal("9999999999"):
        raise ValidationError("El total de la compra supera el máximo permitido.")

    compra = Compra.objects.create(
        grupo=grupo_bloqueado,
        pagador=pagador,
        registrado_por=registrado_por,
        fecha=fecha,
        total=total,
        descripcion=(descripcion or "").strip(),
    )

    for datos in normalizados:
        texto = datos["descripcion"]

        if datos["destino"] == "mascota":
            texto = f"{texto} (mascota)"

        item = Item.objects.create(
            compra=compra,
            descripcion=texto,
            valor=datos["valor"],
        )

        if datos["destino"] == "persona":
            partes = {
                datos["beneficiario"].pk: datos["valor"]
            }
        else:
            partes = repartir(
                datos["valor"],
                miembros,
                pagador=pagador.pk,
            )

        for beneficiario_id, parte in partes.items():
            if parte > 0:
                Asignacion.objects.create(
                    item=item,
                    beneficiario_id=beneficiario_id,
                    valor_asignado=parte,
                )

    Historial.objects.create(
        usuario=registrado_por,
        tipo_registro="Compra",
        id_registro=compra.pk,
        accion="crear",
    )

    return compra

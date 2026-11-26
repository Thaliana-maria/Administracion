from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from auditlog.services import registrar_cambio
from expenses.models import Grupo, Membresia, RevisionCompra


def es_miembro(grupo, usuario):
    if not getattr(usuario, "is_authenticated", False):
        return False

    grupo_id = grupo.pk if isinstance(grupo, Grupo) else grupo

    # El creador conserva acceso al grupo.
    if Grupo.objects.filter(
        pk=grupo_id,
        creador_id=usuario.pk,
    ).exists():
        return True

    return Membresia.objects.filter(
        grupo_id=grupo_id,
        usuario_id=usuario.pk,
        activo=True,
    ).exists()


def es_administrador(grupo, usuario):
    if not getattr(usuario, "is_authenticated", False):
        return False

    grupo_id = grupo.pk if isinstance(grupo, Grupo) else grupo

    # El creador siempre conserva la administración.
    if Grupo.objects.filter(
        pk=grupo_id,
        creador_id=usuario.pk,
    ).exists():
        return True

    return Membresia.objects.filter(
        grupo_id=grupo_id,
        usuario_id=usuario.pk,
        activo=True,
        rol=Membresia.Rol.ADMINISTRADOR,
    ).exists()


def exigir_miembro(grupo, usuario):
    if not es_miembro(grupo, usuario):
        raise PermissionDenied("No perteneces a este grupo.")


def exigir_administrador(grupo, usuario):
    exigir_miembro(grupo, usuario)

    if not es_administrador(grupo, usuario):
        raise PermissionDenied(
            "Se requiere el rol de administrador del grupo."
        )


@transaction.atomic
def establecer_rol(usuario, grupo_id, miembro_id, rol):
    """
    Cambia el rol de una persona dentro de un grupo.

    Reglas:
    - Solo un administrador puede cambiar roles.
    - El creador siempre conserva la administración.
    - No se puede retirar el rol al último administrador activo.
    - Cada cambio queda registrado en auditoría.
    """

    if rol not in Membresia.Rol.values:
        raise ValueError("El rol indicado no es válido.")

    # Bloqueamos el grupo para evitar modificaciones concurrentes
    # que puedan dejarlo sin administradores.
    grupo = Grupo.objects.select_for_update().filter(
        pk=grupo_id
    ).first()

    if grupo is None:
        raise ValidationError("El grupo indicado no existe.")

    exigir_grupo_activo(grupo.pk)
    exigir_administrador(grupo, usuario)

    # Bloqueamos las membresías del grupo.
    membresias = list(
        Membresia.objects.select_for_update().filter(
            grupo_id=grupo_id
        ).order_by("pk")
    )

    membresia = next(
        (
            m for m in membresias
            if m.usuario_id == miembro_id and m.activo
        ),
        None,
    )

    # El creador también debe tener una membresía activa.
    if grupo.creador_id == miembro_id:
        membresia = next(
            (
                m for m in membresias
                if m.usuario_id == miembro_id
            ),
            None,
        )

        if membresia is None:
            raise ValidationError(
                "No se encontró la membresía del creador."
            )

    if membresia is None:
        raise ValidationError(
            "El usuario no es integrante activo del grupo."
        )

    if (
        miembro_id == grupo.creador_id
        and rol != Membresia.Rol.ADMINISTRADOR
    ):
        raise ValidationError(
            "El creador del grupo debe conservar el rol administrador."
        )

    rol_anterior = membresia.rol

    if rol_anterior == rol:
        return membresia

    # No se puede retirar la administración al último administrador.
    if (
        rol_anterior == Membresia.Rol.ADMINISTRADOR
        and rol != Membresia.Rol.ADMINISTRADOR
    ):
        otros_administradores = [
            m
            for m in membresias
            if (
                m.activo
                and m.usuario_id != miembro_id
                and m.rol == Membresia.Rol.ADMINISTRADOR
            )
        ]

        # El creador también cuenta como administrador.
        creador_es_otro_admin = (
            grupo.creador_id != miembro_id
        )

        if not otros_administradores and not creador_es_otro_admin:
            raise ValidationError(
                "No puedes retirar este rol porque es el último "
                "administrador activo del grupo. Asigna primero "
                "otro administrador."
            )

    membresia.rol = rol
    membresia.save(update_fields=["rol"])

    registrar_cambio(
        usuario,
        membresia,
        "cambiar_rol",
        {
            "rol_anterior": rol_anterior,
            "rol_nuevo": rol,
            "grupo_id": grupo_id,
        },
    )

    return membresia


def exigir_puede_editar_compra(compra, usuario):
    exigir_grupo_activo(compra.grupo_id)
    exigir_miembro(compra.grupo_id, usuario)

    if es_administrador(compra.grupo_id, usuario):
        return

    if compra.registrado_por_id != usuario.pk:
        raise PermissionDenied(
            "Solo quien registró la compra o un administrador "
            "puede editarla."
        )


def exigir_puede_editar_pago(pago, usuario):
    exigir_grupo_activo(pago.grupo_id)
    exigir_miembro(pago.grupo_id, usuario)

    if es_administrador(pago.grupo_id, usuario):
        return

    if pago.registrado_por_id != usuario.pk:
        raise PermissionDenied(
            "Solo quien registró el pago o un administrador "
            "puede editarlo."
        )

@transaction.atomic
def retirar_integrante(usuario, grupo_id, miembro_id):
    from django.db.models import Q
    from ledger.models import Obligacion, Pago
    from ledger.services.saldos import calcular_saldos

    grupo = Grupo.objects.select_for_update().get(pk=grupo_id)
    exigir_grupo_activo(grupo.pk)
    exigir_miembro(grupo, usuario)
    if usuario.pk != miembro_id:
        exigir_administrador(grupo, usuario)
    if grupo.creador_id == miembro_id:
        raise ValidationError("No se puede retirar al creador del grupo.")
    membresia = Membresia.objects.select_for_update().filter(
        grupo=grupo, usuario_id=miembro_id, activo=True
    ).first()
    if membresia is None:
        raise ValidationError("El integrante no está activo.")
    if calcular_saldos(grupo).get(miembro_id, 0) != 0:
        raise ValidationError("El integrante debe tener su saldo en cero.")
    if RevisionCompra.objects.filter(compra__grupo=grupo, compra__anulada=False, usuario_id=miembro_id).exclude(estado="aceptada").exists():
        raise ValidationError("El integrante tiene revisiones de compras sin resolver.")
    partes = Q(deudor_id=miembro_id) | Q(acreedor_id=miembro_id)
    if Pago.objects.filter(partes, grupo=grupo, anulada=False, estado="pendiente").exists():
        raise ValidationError("Hay pagos pendientes de confirmación.")
    obligaciones = Obligacion.objects.filter(partes, grupo=grupo, anulada=False,
        asignacion__anulada=False, asignacion__item__anulada=False,
        asignacion__item__compra__anulada=False)
    if any(obligacion.saldo_pendiente > 0 for obligacion in obligaciones):
        raise ValidationError("El integrante tiene obligaciones directas pendientes.")
    membresia.activo = False
    membresia.save(update_fields=["activo"])
    registrar_cambio(usuario, membresia, "retirar", {"antes": "activo", "despues": "inactivo"})
    return membresia


def exigir_grupo_activo(grupo_id):
    if Grupo.objects.filter(pk=grupo_id, archivado=True).exists():
        raise PermissionDenied("El grupo está archivado y es de solo lectura.")


@transaction.atomic
def archivar_grupo(usuario, grupo_id):
    from ledger.models import Obligacion, Pago
    from ledger.services.saldos import calcular_saldos

    grupo = Grupo.objects.select_for_update().get(pk=grupo_id)
    exigir_administrador(grupo, usuario)
    if grupo.creador_id != usuario.pk:
        raise PermissionDenied("Solo el creador puede archivar el grupo.")
    if grupo.archivado:
        return grupo
    if RevisionCompra.objects.filter(compra__grupo=grupo, compra__anulada=False).exclude(estado="aceptada").exists():
        raise ValidationError("Hay revisiones de compras sin resolver.")
    if any(calcular_saldos(grupo).values()):
        raise ValidationError("Todos los saldos deben estar en cero.")
    if Pago.objects.filter(grupo=grupo, anulada=False, estado="pendiente").exists():
        raise ValidationError("Hay pagos pendientes de confirmación.")
    obligaciones = Obligacion.objects.filter(grupo=grupo, anulada=False,
        asignacion__anulada=False, asignacion__item__anulada=False,
        asignacion__item__compra__anulada=False)
    if any(obligacion.saldo_pendiente > 0 for obligacion in obligaciones):
        raise ValidationError("Hay obligaciones directas pendientes.")
    grupo.archivado = True
    grupo.save(update_fields=["archivado"])
    registrar_cambio(usuario, grupo, "archivar", {"antes": "activo", "despues": "archivado"})
    return grupo

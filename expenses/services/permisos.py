from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from auditlog.services import registrar_cambio
from expenses.models import Grupo, Membresia


def es_miembro(grupo, usuario):
    if not getattr(usuario, "is_authenticated", False):
        return False
    grupo_id = grupo.pk if isinstance(grupo, Grupo) else grupo
    return Grupo.objects.filter(pk=grupo_id, creador_id=usuario.pk).exists() or (
        Membresia.objects.filter(
            grupo_id=grupo_id, usuario_id=usuario.pk, activo=True
        ).exists()
    )


def es_administrador(grupo, usuario):
    if not getattr(usuario, "is_authenticated", False):
        return False
    grupo_id = grupo.pk if isinstance(grupo, Grupo) else grupo
    return Grupo.objects.filter(pk=grupo_id, creador_id=usuario.pk).exists() or (
        Membresia.objects.filter(
            grupo_id=grupo_id,
            usuario_id=usuario.pk,
            activo=True,
            rol=Membresia.Rol.ADMINISTRADOR,
        ).exists()
    )


def exigir_miembro(grupo, usuario):
    if not es_miembro(grupo, usuario):
        raise PermissionDenied("No perteneces a este grupo.")


def exigir_administrador(grupo, usuario):
    exigir_miembro(grupo, usuario)
    if not es_administrador(grupo, usuario):
        raise PermissionDenied("Se requiere el rol de administrador del grupo.")


@transaction.atomic
def establecer_rol(usuario, grupo_id, miembro_id, rol):
    exigir_administrador(grupo_id, usuario)
    if rol not in Membresia.Rol.values:
        raise ValueError("El rol indicado no es válido.")
    if (
        rol != Membresia.Rol.ADMINISTRADOR
        and Grupo.objects.filter(pk=grupo_id, creador_id=miembro_id).exists()
    ):
        raise ValidationError("El creador del grupo debe conservar el rol administrador.")

    membresia, creada = Membresia.objects.get_or_create(
        grupo_id=grupo_id,
        usuario_id=miembro_id,
        defaults={"rol": rol},
    )
    rol_anterior = membresia.rol
    if not creada and rol_anterior != rol:
        membresia.rol = rol
        membresia.save(update_fields=["rol"])

    if creada or rol_anterior != rol:
        registrar_cambio(
            usuario,
            membresia,
            "cambiar_rol",
            {"rol_anterior": rol_anterior if not creada else None, "rol_nuevo": rol},
        )
    return membresia


def exigir_puede_editar_compra(compra, usuario):
    exigir_miembro(compra.grupo_id, usuario)
    if es_administrador(compra.grupo_id, usuario):
        return
    if compra.registrado_por_id != usuario.pk:
        raise PermissionDenied("Solo quien registró la compra o un administrador puede editarla.")


def exigir_puede_editar_pago(pago, usuario):
    exigir_miembro(pago.grupo_id, usuario)
    if es_administrador(pago.grupo_id, usuario):
        return
    if pago.registrado_por_id != usuario.pk:
        raise PermissionDenied("Solo quien registró el pago o un administrador puede editarlo.")

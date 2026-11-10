from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from auditlog.services import registrar_cambio
from expenses.models import Grupo, Membresia
from expenses.services.permisos import exigir_administrador

Usuario = get_user_model()


def _usuarios_por_correo(correos):
    emails = {
        correo.strip().casefold()
        for correo in correos.replace(",", "\n").splitlines()
        if correo.strip()
    }
    filtro = Q()
    for email in emails:
        filtro |= Q(email__iexact=email)
    usuarios = list(Usuario.objects.filter(filtro)) if emails else []
    encontrados = {usuario.email.casefold() for usuario in usuarios}
    faltantes = sorted(emails - encontrados)
    if faltantes:
        raise ValidationError(
            "No existen cuentas para estos correos: " + ", ".join(faltantes)
        )
    return usuarios


@transaction.atomic
def crear_grupo(creador, *, nombre, correos_integrantes=""):
    nombre = nombre.strip()
    if not nombre:
        raise ValidationError("El nombre del grupo es obligatorio.")
    integrantes = _usuarios_por_correo(correos_integrantes)
    grupo = Grupo.objects.create(nombre=nombre, creador=creador)
    Membresia.objects.create(
        grupo=grupo,
        usuario=creador,
        rol=Membresia.Rol.ADMINISTRADOR,
    )
    for integrante in integrantes:
        if integrante.pk == creador.pk:
            continue
        Membresia.objects.get_or_create(
            grupo=grupo,
            usuario=integrante,
            defaults={"rol": Membresia.Rol.MIEMBRO, "activo": True},
        )
    registrar_cambio(
        creador,
        grupo,
        "crear",
        {
            "nombre": nombre,
            "integrantes": [integrante.pk for integrante in integrantes],
        },
    )
    return grupo


@transaction.atomic
def agregar_integrantes(usuario, grupo_id, correos_integrantes):
    exigir_administrador(grupo_id, usuario)
    integrantes = _usuarios_por_correo(correos_integrantes)
    grupo = Grupo.objects.get(pk=grupo_id)
    agregados = []
    for integrante in integrantes:
        membresia, creada = Membresia.objects.get_or_create(
            grupo=grupo,
            usuario=integrante,
            defaults={"rol": Membresia.Rol.MIEMBRO, "activo": True},
        )
        estaba_activa = not creada and membresia.activo
        if not creada and not membresia.activo:
            membresia.activo = True
            membresia.save(update_fields=["activo"])
        if creada or not estaba_activa:
            agregados.append(integrante.pk)
    if agregados:
        registrar_cambio(
            usuario,
            grupo,
            "agregar_integrantes",
            {"integrantes": agregados},
        )
    return agregados


@transaction.atomic
def retirar_integrante(usuario, grupo_id, miembro_id):
    exigir_administrador(grupo_id, usuario)
    grupo = Grupo.objects.get(pk=grupo_id)
    if grupo.creador_id == miembro_id:
        raise ValidationError("El creador del grupo no se puede retirar.")
    membresia = Membresia.objects.select_for_update().filter(
        grupo=grupo,
        usuario_id=miembro_id,
        activo=True,
    ).first()
    if membresia is None:
        raise ValidationError("El integrante no pertenece activamente al grupo.")
    membresia.activo = False
    membresia.save(update_fields=["activo"])
    registrar_cambio(
        usuario,
        grupo,
        "retirar_integrante",
        {"integrante_id": miembro_id},
    )
    return membresia

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from auditlog.models import Historial
from expenses.models import Asignacion, Compra, Grupo, Item, Membresia
from expenses.services.reparto import repartir

DESTINOS = ("todos", "persona", "mascota")


def registrar_grupo(creador, nombre):
    """Crea un grupo y deja al creador como primer integrante (RF-01)."""
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValidationError("El nombre del grupo es obligatorio.")
    with transaction.atomic():
        grupo = Grupo.objects.create(nombre=nombre, creador=creador)
        Membresia.objects.create(grupo=grupo, usuario=creador)
        Historial.objects.create(
            usuario=creador, tipo_registro="Grupo", id_registro=grupo.id, accion="crear"
        )
    return grupo


def agregar_integrante(grupo, usuario, quien_agrega):
    """Agrega un usuario existente al grupo (RF-01)."""
    if not Membresia.objects.filter(grupo=grupo, usuario=quien_agrega).exists():
        raise ValidationError("Solo los integrantes del grupo pueden agregar personas.")
    if Membresia.objects.filter(grupo=grupo, usuario=usuario).exists():
        raise ValidationError("Esa persona ya es integrante del grupo.")
    with transaction.atomic():
        membresia = Membresia.objects.create(grupo=grupo, usuario=usuario)
        Historial.objects.create(
            usuario=quien_agrega,
            tipo_registro="Membresia",
            id_registro=membresia.id,
            accion="crear",
        )
    return membresia


def _valor_entero_positivo(bruto, posicion):
    try:
        valor = Decimal(str(bruto))
    except (InvalidOperation, ValueError):
        raise ValidationError(f"Ítem {posicion}: el valor no es un número válido.")
    if valor <= 0:
        raise ValidationError(f"Ítem {posicion}: el valor debe ser mayor que cero.")
    if valor != valor.to_integral_value():
        raise ValidationError(f"Ítem {posicion}: el valor debe estar en pesos enteros.")
    return valor


def validar_items(grupo, items):
    """RF-08: valida los ítems antes de guardar y devuelve una lista normalizada.

    Cada ítem es un diccionario con: descripcion, valor, destino y,
    cuando el destino es "persona", beneficiario (usuario o id).
    """
    if not items:
        raise ValidationError("La compra debe tener por lo menos un ítem.")

    miembros = {m.usuario_id: m.usuario for m in grupo.miembros.select_related("usuario")}
    normalizados = []
    for posicion, item in enumerate(items, start=1):
        descripcion = (item.get("descripcion") or "").strip()
        if not descripcion:
            raise ValidationError(f"Ítem {posicion}: la descripción es obligatoria.")
        valor = _valor_entero_positivo(item.get("valor"), posicion)

        destino = item.get("destino") or "todos"
        if destino not in DESTINOS:
            raise ValidationError(f"Ítem {posicion}: el destino «{destino}» no es válido.")

        beneficiario = None
        if destino == "persona":
            bruto = item.get("beneficiario")
            beneficiario_id = getattr(bruto, "id", bruto)
            if beneficiario_id in (None, ""):
                raise ValidationError(f"Ítem {posicion}: debe elegir a quién se le asigna.")
            beneficiario = miembros.get(int(beneficiario_id))
            if beneficiario is None:
                raise ValidationError(
                    f"Ítem {posicion}: la persona asignada no pertenece al grupo."
                )
        normalizados.append(
            {
                "descripcion": descripcion,
                "valor": valor,
                "destino": destino,
                "beneficiario": beneficiario,
            }
        )
    return normalizados, list(miembros.values())


def registrar_compra(grupo, pagador, fecha, descripcion, items, registrado_por=None):
    """Registra una compra con sus ítems y asignaciones (RF-02, RF-03, RF-04).

    - destino "todos": se reparte entre todos los integrantes con RN-05.
    - destino "mascota": se reparte igual que "todos" (el gasto es de la casa)
      y se marca con «(mascota)» en la descripción del ítem.
    - destino "persona": todo el valor va a esa persona.
    El total de la compra es la suma de los ítems.
    """
    registrado_por = registrado_por or pagador
    es_miembro = Membresia.objects.filter(grupo=grupo, usuario=registrado_por).exists()
    if not es_miembro:
        raise ValidationError("Solo los integrantes del grupo pueden registrar compras.")
    if not Membresia.objects.filter(grupo=grupo, usuario=pagador).exists():
        raise ValidationError("El pagador debe ser integrante del grupo.")

    normalizados, miembros = validar_items(grupo, items)
    total = sum((item["valor"] for item in normalizados), Decimal("0"))

    with transaction.atomic():
        compra = Compra.objects.create(
            grupo=grupo,
            pagador=pagador,
            fecha=fecha,
            total=total,
            descripcion=(descripcion or "").strip(),
        )
        for datos in normalizados:
            texto = datos["descripcion"]
            if datos["destino"] == "mascota":
                texto = f"{texto} (mascota)"
            item = Item.objects.create(compra=compra, descripcion=texto, valor=datos["valor"])

            if datos["destino"] == "persona":
                partes = {datos["beneficiario"].id: datos["valor"]}
            else:
                partes = repartir(datos["valor"], miembros, pagador=pagador.id)

            for beneficiario_id, parte in partes.items():
                if parte > 0:  # con valores muy pequeños algunas partes quedan en 0
                    Asignacion.objects.create(
                        item=item, beneficiario_id=beneficiario_id, valor_asignado=parte
                    )

        Historial.objects.create(
            usuario=registrado_por,
            tipo_registro="Compra",
            id_registro=compra.id,
            accion="crear",
        )
    return compra
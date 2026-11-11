from auditlog.models import Historial


def registrar_cambio(usuario, instancia, accion, detalles):
    return Historial.objects.create(
        usuario=usuario,
        tipo_registro=instancia._meta.label,
        id_registro=instancia.pk,
        accion=accion,
        detalles=detalles,
    )

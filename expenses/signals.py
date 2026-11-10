from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from expenses.models import Asignacion


@receiver(pre_save, sender=Asignacion)
def proteger_obligaciones_con_abonos(sender, instance, **kwargs):
    if not instance.pk:
        return

    anteriores = sender.objects.filter(pk=instance.pk).values(
        "valor_asignado",
        "beneficiario_id",
        "item_id",
        "anulada",
    ).first()
    try:
        obligacion = instance.obligacion
    except ObjectDoesNotExist:
        return

    if not obligacion.aplicaciones.filter(anulada=False, pago__anulada=False).exists():
        return
    anulacion_sin_edicion = (
        instance.anulada
        and anteriores is not None
        and instance.valor_asignado == anteriores["valor_asignado"]
        and instance.beneficiario_id == anteriores["beneficiario_id"]
        and instance.item_id == anteriores["item_id"]
    )
    if not anulacion_sin_edicion:
        raise ValidationError(
            "No se puede modificar una asignación con pagos aplicados; "
            "primero debe corregirse el historial de pagos."
        )


@receiver(post_save, sender=Asignacion)
def sincronizar_obligacion(sender, instance, **kwargs):
    from ledger.models import Obligacion

    compra = instance.item.compra
    if instance.beneficiario_id == compra.pagador_id:
        Obligacion.objects.filter(asignacion=instance).update(anulada=True)
        return

    Obligacion.objects.update_or_create(
        asignacion=instance,
        defaults={
            "grupo_id": compra.grupo_id,
            "deudor_id": instance.beneficiario_id,
            "acreedor_id": compra.pagador_id,
            "monto": instance.valor_asignado,
            "anulada": (
                instance.anulada or instance.item.anulada or compra.anulada
            ),
        },
    )

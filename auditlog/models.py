from django.conf import settings
from django.db import models


class RegistroAnulable(models.Model):
    anulada = models.BooleanField(default=False)
    anulada_en = models.DateTimeField(null=True, blank=True)
    anulada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_anulaciones",
    )

    class Meta:
        abstract = True


class Historial(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    tipo_registro = models.CharField(max_length=50)
    id_registro = models.PositiveIntegerField()
    accion = models.CharField(max_length=30)
    detalles = models.JSONField(default=dict, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["usuario", "fecha"]),
            models.Index(fields=["tipo_registro", "id_registro"]),
        ]

    def __str__(self):
        return f"{self.tipo_registro} - {self.accion}"

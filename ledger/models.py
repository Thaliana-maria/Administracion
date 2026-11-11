from django.conf import settings
from django.db import models
from django.db.models import Q
from expenses.models import Grupo


class Pago(models.Model):
    grupo = models.ForeignKey(Grupo, on_delete=models.PROTECT, related_name="pagos")
    deudor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pagos_enviados"
    )
    acreedor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pagos_recibidos"
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    fecha = models.DateField()

    class Meta:
        indexes = [
            models.Index(fields=["grupo", "fecha"]),
            models.Index(fields=["deudor", "fecha"]),
            models.Index(fields=["acreedor", "fecha"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(monto__gt=0), name="pago_monto_positivo"),
            models.CheckConstraint(condition=~Q(deudor=models.F("acreedor")), name="pago_personas_distintas"),
        ]

    def __str__(self):
        return f"{self.deudor} paga a {self.acreedor}: {self.monto}"

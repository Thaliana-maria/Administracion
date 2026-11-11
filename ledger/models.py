from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from auditlog.models import RegistroAnulable
from expenses.models import Grupo, Asignacion


class Pago(RegistroAnulable):
    grupo = models.ForeignKey(Grupo, on_delete=models.PROTECT, related_name="pagos")
    deudor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pagos_enviados"
    )
    acreedor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pagos_recibidos"
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    fecha = models.DateField()
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pagos_registrados",
    )

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


class Obligacion(models.Model):
    asignacion = models.OneToOneField(
        Asignacion, on_delete=models.PROTECT, related_name="obligacion"
    )
    grupo = models.ForeignKey(Grupo, on_delete=models.PROTECT, related_name="obligaciones")
    deudor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="obligaciones_deuda"
    )
    acreedor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="obligaciones_cobro",
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    anulada = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(monto__gt=0), name="obligacion_monto_positivo"),
        ]
        indexes = [
            models.Index(fields=["grupo", "deudor", "acreedor"]),
        ]

    @property
    def monto_aplicado(self):
        return self.aplicaciones.filter(
            anulada=False, pago__anulada=False
        ).aggregate(total=models.Sum("monto"))["total"] or Decimal("0.00")

    @property
    def saldo_pendiente(self):
        return self.monto - self.monto_aplicado


class AplicacionPago(models.Model):
    pago = models.ForeignKey(Pago, on_delete=models.PROTECT, related_name="aplicaciones")
    obligacion = models.ForeignKey(
        Obligacion, on_delete=models.PROTECT, related_name="aplicaciones"
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    anulada = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(monto__gt=0), name="aplicacion_monto_positivo"),
        ]
        indexes = [models.Index(fields=["obligacion", "anulada"])]

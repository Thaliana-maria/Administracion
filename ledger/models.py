from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from auditlog.models import RegistroAnulable
from expenses.models import Grupo, Asignacion


class Pago(RegistroAnulable):
    estado = models.CharField(max_length=12, choices=[("pendiente", "Pendiente"), ("confirmado", "Confirmado"), ("rechazado", "Rechazado")], default="confirmado")
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
        pagos = self.aplicaciones.filter(
            anulada=False, pago__anulada=False, pago__estado="confirmado"
        ).aggregate(total=models.Sum("monto"))["total"] or Decimal("0.00")

        compensaciones = self.tramos_compensacion.filter(
            compensacion__estado="aplicada"
        ).aggregate(total=models.Sum("monto"))["total"] or Decimal("0.00")
        return pagos + compensaciones

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


class Compensacion(models.Model):
    grupo = models.ForeignKey(Grupo, on_delete=models.PROTECT, related_name="compensaciones")
    solicitante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="compensaciones_solicitadas")
    deudor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="compensaciones_enviadas")
    acreedor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="compensaciones_recibidas")
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    estado = models.CharField(max_length=12, choices=[("pendiente", "Pendiente"), ("aprobada", "Aprobada"), ("rechazada", "Rechazada"), ("cancelada", "Cancelada"), ("aplicada", "Aplicada")], default="pendiente")
    fecha = models.DateTimeField(auto_now_add=True)
    clave = models.UUIDField(unique=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(monto__gt=0), name="compensacion_monto_positivo"),
            models.CheckConstraint(condition=~Q(deudor=models.F("acreedor")), name="compensacion_personas_distintas"),
        ]


class AprobacionCompensacion(models.Model):
    compensacion = models.ForeignKey(Compensacion, on_delete=models.PROTECT, related_name="aprobaciones")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    estado = models.CharField(max_length=10, choices=[("pendiente", "Pendiente"), ("aceptada", "Aceptada"), ("rechazada", "Rechazada")], default="pendiente")
    fecha_respuesta = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["compensacion", "usuario"], name="compensacion_aprobacion_unica"),
        ]


class TramoCompensacion(models.Model):
    compensacion = models.ForeignKey(Compensacion, on_delete=models.PROTECT, related_name="tramos")
    obligacion = models.ForeignKey(Obligacion, on_delete=models.PROTECT, related_name="tramos_compensacion")
    orden = models.PositiveIntegerField()
    monto = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(monto__gt=0), name="tramo_compensacion_monto_positivo"),
            models.UniqueConstraint(fields=["compensacion", "obligacion"], name="compensacion_obligacion_unica"),
        ]

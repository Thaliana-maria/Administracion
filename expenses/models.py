from django.conf import settings
from django.db import models
from django.db.models import Q
from auditlog.models import RegistroAnulable


class Grupo(models.Model):
    nombre = models.CharField(max_length=100)
    creador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["creador", "fecha_creacion"])]

    def __str__(self):
        return self.nombre


class Membresia(models.Model):
    class Rol(models.TextChoices):
        ADMINISTRADOR = "administrador", "Administrador"
        MIEMBRO = "miembro", "Miembro"

    grupo = models.ForeignKey(Grupo, on_delete=models.CASCADE, related_name="miembros")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.MIEMBRO)
    activo = models.BooleanField(default=True)
    fecha_union = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["grupo", "usuario"], name="un_miembro_por_grupo")
        ]
        indexes = [models.Index(fields=["usuario", "grupo"])]

    def __str__(self):
        return f"{self.usuario} - {self.grupo}"


class Compra(RegistroAnulable):
    grupo = models.ForeignKey(Grupo, on_delete=models.PROTECT, related_name="compras")
    pagador = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="compras_pagadas"
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="compras_registradas",
    )
    fecha = models.DateField()
    total = models.DecimalField(max_digits=12, decimal_places=2)
    impuesto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    descuento = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    descripcion = models.CharField(max_length=150, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["grupo", "fecha"]),
            models.Index(fields=["pagador", "fecha"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(total__gt=0), name="compra_total_positivo"),
            models.CheckConstraint(condition=Q(impuesto__gte=0), name="compra_impuesto_no_negativo"),
            models.CheckConstraint(condition=Q(descuento__gte=0), name="compra_descuento_no_negativo"),
        ]

    def __str__(self):
        return f"Compra {self.id} - {self.total}"


class Item(RegistroAnulable):
    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name="items")
    descripcion = models.CharField(max_length=150)
    valor = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        indexes = [models.Index(fields=["compra"])]
        constraints = [
            models.CheckConstraint(condition=Q(valor__gt=0), name="item_valor_positivo")
        ]

    def __str__(self):
        return self.descripcion


class Asignacion(RegistroAnulable):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="asignaciones")
    beneficiario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    valor_asignado = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item", "beneficiario"],
                condition=Q(anulada=False),
                name="una_asignacion_activa_por_persona_item",
            ),
            models.CheckConstraint(condition=Q(valor_asignado__gt=0), name="asignacion_valor_positivo"),
        ]
        indexes = [models.Index(fields=["beneficiario", "item"])]

    def __str__(self):
        return f"{self.beneficiario}: {self.valor_asignado}"


class AjusteCompra(models.Model):
    compra = models.ForeignKey(
        Compra, on_delete=models.PROTECT, related_name="ajustes_asignados"
    )
    beneficiario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ajustes_compras",
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["compra", "beneficiario"],
                name="un_ajuste_por_beneficiario_compra",
            )
        ]

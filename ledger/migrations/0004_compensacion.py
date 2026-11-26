from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("ledger", "0003_pago_estado"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Compensacion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("monto", models.DecimalField(max_digits=12, decimal_places=2)),
                ("estado", models.CharField(max_length=12, choices=[("pendiente", "Pendiente"), ("aprobada", "Aprobada"), ("rechazada", "Rechazada"), ("cancelada", "Cancelada"), ("aplicada", "Aplicada")], default="pendiente")),
                ("fecha", models.DateTimeField(auto_now_add=True)),
                ("clave", models.UUIDField(unique=True)),
                ("grupo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="compensaciones", to="expenses.grupo")),
                ("solicitante", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="compensaciones_solicitadas", to=settings.AUTH_USER_MODEL)),
                ("deudor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="compensaciones_enviadas", to=settings.AUTH_USER_MODEL)),
                ("acreedor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="compensaciones_recibidas", to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints": [
                models.CheckConstraint(condition=models.Q(monto__gt=0), name="compensacion_monto_positivo"),
                models.CheckConstraint(condition=~models.Q(deudor=models.F("acreedor")), name="compensacion_personas_distintas"),
            ]},
        ),
        migrations.CreateModel(
            name="AprobacionCompensacion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("estado", models.CharField(max_length=10, choices=[("pendiente", "Pendiente"), ("aceptada", "Aceptada"), ("rechazada", "Rechazada")], default="pendiente")),
                ("fecha_respuesta", models.DateTimeField(null=True, blank=True)),
                ("compensacion", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="aprobaciones", to="ledger.compensacion")),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints": [models.UniqueConstraint(fields=["compensacion", "usuario"], name="compensacion_aprobacion_unica")]},
        ),
        migrations.CreateModel(
            name="TramoCompensacion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("orden", models.PositiveIntegerField()),
                ("monto", models.DecimalField(max_digits=12, decimal_places=2)),
                ("compensacion", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="tramos", to="ledger.compensacion")),
                ("obligacion", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="tramos_compensacion", to="ledger.obligacion")),
            ],
            options={"constraints": [
                models.CheckConstraint(condition=models.Q(monto__gt=0), name="tramo_compensacion_monto_positivo"),
                models.UniqueConstraint(fields=["compensacion", "obligacion"], name="compensacion_obligacion_unica"),
            ]},
        ),
    ]

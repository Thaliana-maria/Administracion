from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0008_operacionregistro"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="RevisionCompra",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("estado", models.CharField(max_length=12, choices=[("pendiente", "Pendiente"), ("aceptada", "Aceptada"), ("objetada", "Objetada")], default="pendiente")),
                ("compra", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="revisiones", to="expenses.compra")),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("compra", "usuario"), name="una_revision_por_compra_usuario")]},
        ),
    ]

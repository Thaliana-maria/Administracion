from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0007_grupo_archivado"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="OperacionRegistro",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("clave", models.UUIDField(unique=True)),
                ("tipo", models.CharField(max_length=10)),
                ("registro_id", models.PositiveIntegerField(null=True)),
                ("grupo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="expenses.grupo")),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ledger", "0004_compensacion"),
    ]

    operations = [
        migrations.AddField(
            model_name="compensacion",
            name="fecha_aplicacion",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

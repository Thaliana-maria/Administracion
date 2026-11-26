from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ledger", "0002_pago_anulada_pago_anulada_en_pago_anulada_por_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="pago",
            name="estado",
            field=models.CharField(max_length=12, choices=[("pendiente", "Pendiente"), ("confirmado", "Confirmado"), ("rechazado", "Rechazado")], default="confirmado"),
        ),
    ]

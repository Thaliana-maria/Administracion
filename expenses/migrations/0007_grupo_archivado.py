from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0006_compra_compra_impuesto_no_negativo_and_more"),
    ]

    operations = [
        migrations.AddField(model_name="grupo", name="archivado", field=models.BooleanField(default=False)),
    ]

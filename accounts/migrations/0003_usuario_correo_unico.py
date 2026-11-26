from django.db import migrations, models
from django.db.models.functions import Lower


def verificar_correos(apps, schema_editor):
    Usuario = apps.get_model("accounts", "Usuario")
    usuarios = Usuario.objects.using(schema_editor.connection.alias)
    duplicados = usuarios.annotate(correo=Lower("email")).values("correo").annotate(cantidad=models.Count("pk")).filter(cantidad__gt=1)
    if duplicados.exists():
        raise RuntimeError("Existen correos duplicados al ignorar mayúsculas. Revisa las cuentas antes de continuar.")


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_usuario_autorizacion_datos")]
    operations = [
        migrations.RunPython(verificar_correos, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="usuario",
            constraint=models.UniqueConstraint(Lower("email"), name="usuario_correo_unico_minusculas"),
        ),
    ]

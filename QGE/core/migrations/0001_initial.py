import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Household",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("is_active", models.BooleanField(default=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_households", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="PrivacyConsent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("accepted_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("policy_version", models.CharField(default="1.0", max_length=20)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="privacy_consent", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="Membership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("ADMIN", "Administrador"), ("MEMBER", "Miembro")], default="MEMBER", max_length=10)),
                ("is_active", models.BooleanField(default=True)),
                ("joined_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("household", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="core.household")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="household_memberships", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["joined_at", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="membership",
            constraint=models.UniqueConstraint(fields=("household", "user"), name="unique_household_membership"),
        ),
    ]

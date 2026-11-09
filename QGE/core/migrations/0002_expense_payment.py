from django.conf import settings
from django.db import migrations, models
from django.db.models import deletion
from django.utils import timezone

class Migration(migrations.Migration):
    dependencies = [('core', '0001_initial'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name='Expense',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('description', models.CharField(max_length=180)),
                ('amount', models.DecimalField(max_digits=12, decimal_places=2)),
                ('created_at', models.DateTimeField(default=timezone.now)),
                ('created_by', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=deletion.PROTECT)),
                ('household', models.ForeignKey(to='core.household', related_name='expenses', on_delete=deletion.CASCADE)),
            ],
            options={'ordering': ['-created_at', '-id']},
        ),
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('amount', models.DecimalField(max_digits=12, decimal_places=2)),
                ('note', models.CharField(max_length=200, blank=True)),
                ('created_at', models.DateTimeField(default=timezone.now)),
                ('household', models.ForeignKey(to='core.household', related_name='payments', on_delete=deletion.CASCADE)),
                ('payer', models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='payments_made', on_delete=deletion.PROTECT)),
                ('receiver', models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='payments_received', on_delete=deletion.PROTECT)),
            ],
            options={'ordering': ['-created_at', '-id']},
        ),
    ]

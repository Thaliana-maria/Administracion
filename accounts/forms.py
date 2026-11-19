

from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Usuario


class RegistroForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = ["first_name", "last_name", "email"]
        labels = {
            "first_name": "Nombre",
            "last_name": "Apellido",
            "email": "Correo electrónico",
        }


class PerfilForm(forms.ModelForm):
    """Permite editar únicamente los datos personales de la propia cuenta."""

    class Meta:
        model = Usuario
        fields = ["first_name", "last_name", "email"]
        labels = {
            "first_name": "Nombre",
            "last_name": "Apellido",
            "email": "Correo electrónico",
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        duplicado = Usuario.objects.filter(
            email__iexact=email
        ).exclude(pk=self.instance.pk)

        if duplicado.exists():
            raise forms.ValidationError(
                "Ya existe una cuenta registrada con ese correo."
            )

        return email

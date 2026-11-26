

from django import forms
from django.utils import timezone
from django.contrib.auth.forms import UserCreationForm
from .models import Usuario


class RegistroForm(UserCreationForm):
    aceptar_datos = forms.BooleanField(required=True, label="Autorizo el tratamiento de mis datos personales para gestionar mi cuenta y los gastos compartidos.", error_messages={"required": "Debes autorizar el tratamiento de datos para crear tu cuenta."})

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.autorizacion_datos = timezone.now()
        if commit:
            usuario.save()
        return usuario

    class Meta:
        model = Usuario
        fields = ["first_name", "last_name", "email"]
        labels = {
            "first_name": "Nombre",
            "last_name": "Apellido",
            "email": "Correo electrónico",
        }

    def clean_email(self):
        correo = self.cleaned_data["email"].strip().lower()
        if Usuario.objects.filter(email__iexact=correo).exists():
            raise forms.ValidationError("Este correo ya está registrado.")
        return correo


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

from django import forms
from django.utils import timezone

from accounts.models import Usuario

DESTINO_OPCIONES = [
    ("todos", "Todos"),
    ("persona", "Una persona"),
    ("mascota", "Mascota"),
]


class GrupoForm(forms.Form):
    nombre = forms.CharField(label="Nombre del grupo", max_length=100)


class IntegranteForm(forms.Form):
    email = forms.EmailField(label="Correo del integrante")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        try:
            self.usuario = Usuario.objects.get(email__iexact=email)
        except Usuario.DoesNotExist:
            raise forms.ValidationError(
                "No existe un usuario con ese correo. Debe registrarse primero."
            )
        return email


class CompraForm(forms.Form):
    pagador = forms.ModelChoiceField(queryset=Usuario.objects.none(), label="Quién pagó")
    fecha = forms.DateField(
        label="Fecha",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    descripcion = forms.CharField(label="Descripción", max_length=150, required=False)

    def __init__(self, *args, miembros=None, **kwargs):
        super().__init__(*args, **kwargs)
        if miembros is not None:
            self.fields["pagador"].queryset = miembros


class ItemForm(forms.Form):
    descripcion = forms.CharField(label="Ítem", max_length=150)
    valor = forms.DecimalField(label="Valor", min_value=1, max_digits=12, decimal_places=0)
    destino = forms.ChoiceField(label="Para", choices=DESTINO_OPCIONES, initial="todos")
    beneficiario = forms.ModelChoiceField(
        queryset=Usuario.objects.none(), label="Persona", required=False
    )

    def __init__(self, *args, miembros=None, **kwargs):
        super().__init__(*args, **kwargs)
        if miembros is not None:
            self.fields["beneficiario"].queryset = miembros

    def clean(self):
        datos = super().clean()
        if datos.get("destino") == "persona" and not datos.get("beneficiario"):
            self.add_error("beneficiario", "Elige a quién se le asigna este ítem.")
        return datos

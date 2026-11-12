
from django import forms
from django.utils import timezone
from django.contrib.auth import get_user_model

from accounts.models import Usuario
from expenses.models import Membresia

UsuarioActual = get_user_model()

DESTINO_OPCIONES = [
    ("todos", "Todos"),
    ("persona", "Una persona"),
    ("mascota", "Mascota"),
]


def integrantes_activos(grupo):
    return UsuarioActual.objects.filter(
        membresia__grupo=grupo,
        membresia__activo=True,
    ).distinct().order_by("first_name", "last_name", "email")


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
    pagador = forms.ModelChoiceField(
        queryset=Usuario.objects.none(),
        label="Quién pagó"
    )
    fecha = forms.DateField(
        label="Fecha",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    descripcion = forms.CharField(
        label="Descripción",
        max_length=150,
        required=False
    )

    def __init__(self, *args, miembros=None, **kwargs):
        super().__init__(*args, **kwargs)
        if miembros is not None:
            self.fields["pagador"].queryset = miembros


class ItemForm(forms.Form):
    descripcion = forms.CharField(label="Ítem", max_length=150)
    valor = forms.DecimalField(
        label="Valor",
        min_value=1,
        max_digits=12,
        decimal_places=0
    )
    destino = forms.ChoiceField(
        label="Para",
        choices=DESTINO_OPCIONES,
        initial="todos"
    )
    beneficiario = forms.ModelChoiceField(
        queryset=Usuario.objects.none(),
        label="Persona",
        required=False
    )

    def __init__(self, *args, miembros=None, **kwargs):
        super().__init__(*args, **kwargs)
        if miembros is not None:
            self.fields["beneficiario"].queryset = miembros

    def clean(self):
        datos = super().clean()
        if datos.get("destino") == "persona" and not datos.get("beneficiario"):
            self.add_error(
                "beneficiario",
                "Elige a quién se le asigna este ítem."
            )
        return datos


class EditarCompraForm(forms.Form):
    fecha = forms.DateField(
        label="Fecha",
        widget=forms.DateInput(attrs={"type": "date"})
    )
    descripcion = forms.CharField(
        max_length=150,
        required=False,
        label="Descripción"
    )


class EditarItemForm(forms.Form):
    descripcion = forms.CharField(max_length=150, label="Descripción")
    valor = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        label="Valor"
    )
    beneficiarios = forms.ModelMultipleChoiceField(
        queryset=UsuarioActual.objects.none(),
        label="Beneficiarios",
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, grupo, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["beneficiarios"].queryset = integrantes_activos(grupo)


class EditarPagoForm(forms.Form):
    monto = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        label="Monto"
    )
    fecha = forms.DateField(
        label="Fecha",
        widget=forms.DateInput(attrs={"type": "date"})
    )

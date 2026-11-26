
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
    clave_operacion = forms.UUIDField(widget=forms.HiddenInput)
    total_esperado = forms.DecimalField(label="Total de la compra (COP)", max_digits=12, decimal_places=2, min_value=0.01, required=False)
    impuesto = forms.DecimalField(label="IVA adicional (COP)", help_text="Deja en cero si el impuesto ya está incluido o no aplica.", max_digits=12, decimal_places=2, min_value=0, required=False, initial=0)
    descuento = forms.DecimalField(label="Descuento general adicional (COP)", help_text="Deja en cero si los precios ya incluyen las rebajas.", max_digits=12, decimal_places=2, min_value=0, required=False, initial=0)

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
        label="Valor del ítem (COP)",
        help_text="Si tiene un descuento individual, registra el precio final del producto.",
        min_value=1,
        max_digits=10,
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
    pagador = forms.ModelChoiceField(queryset=UsuarioActual.objects.none(), label="Quién pagó", required=False)

    def __init__(self, *args, grupo=None, **kwargs):
        super().__init__(*args, **kwargs)
        if grupo is not None:
            self.fields["pagador"].queryset = (integrantes_activos(grupo) | UsuarioActual.objects.filter(pk=grupo.creador_id)).distinct()

    impuesto = forms.DecimalField(label="IVA adicional (COP)", max_digits=12, decimal_places=2, min_value=0, required=False)
    descuento = forms.DecimalField(label="Descuento general (COP)", max_digits=12, decimal_places=2, min_value=0, required=False)
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
        max_digits=10,
        decimal_places=0,
        min_value=1,
        label="Valor"
    )
    beneficiarios = forms.ModelMultipleChoiceField(
        queryset=UsuarioActual.objects.none(),
        label="Beneficiarios",
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, grupo, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["beneficiarios"].queryset = (integrantes_activos(grupo) | UsuarioActual.objects.filter(pk=grupo.creador_id)).distinct()


class EditarPagoForm(forms.Form):
    monto = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
        label="Monto"
    )
    fecha = forms.DateField(
        label="Fecha",
        widget=forms.DateInput(attrs={"type": "date"})
    )


class PagoForm(forms.Form):
    clave_operacion = forms.UUIDField(widget=forms.HiddenInput)
    deudor = forms.ModelChoiceField(queryset=Usuario.objects.none(), label="Quién pagó")
    acreedor = forms.ModelChoiceField(queryset=Usuario.objects.none(), label="Quién recibió")
    monto = forms.DecimalField(label="Valor (COP)", max_digits=12, decimal_places=2, min_value=0.01)
    fecha = forms.DateField(label="Fecha", initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))

    def __init__(self, *args, miembros, usuario, administrador, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["deudor"].queryset = miembros if administrador else miembros.filter(pk=usuario.pk)
        self.fields["acreedor"].queryset = miembros

    def clean(self):
        datos = super().clean()
        if datos.get("deudor") and datos.get("deudor") == datos.get("acreedor"):
            self.add_error("acreedor", "Elige una persona diferente al pagador.")
        return datos

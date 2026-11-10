from django import forms
from django.contrib.auth import get_user_model

from expenses.models import Membresia

Usuario = get_user_model()


def integrantes_activos(grupo):
    return Usuario.objects.filter(
        membresia__grupo=grupo,
        membresia__activo=True,
    ).distinct().order_by("first_name", "last_name", "email")


class EditarCompraForm(forms.Form):
    fecha = forms.DateField(label="Fecha", widget=forms.DateInput(attrs={"type": "date"}))
    descripcion = forms.CharField(max_length=150, required=False, label="Descripción")


class EditarItemForm(forms.Form):
    descripcion = forms.CharField(max_length=150, label="Descripción")
    valor = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0, label="Valor")
    beneficiarios = forms.ModelMultipleChoiceField(
        queryset=Usuario.objects.none(),
        label="Beneficiarios",
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, grupo, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["beneficiarios"].queryset = integrantes_activos(grupo)


class EditarPagoForm(forms.Form):
    monto = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0, label="Monto")
    fecha = forms.DateField(label="Fecha", widget=forms.DateInput(attrs={"type": "date"}))

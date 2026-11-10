from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.forms import formset_factory
from django.utils import timezone

from expenses.models import Grupo, Membresia
from ledger.models import Obligacion

Usuario = get_user_model()


class GrupoForm(forms.Form):
    nombre = forms.CharField(max_length=100, label="Nombre del grupo")
    correos_integrantes = forms.CharField(
        required=False,
        label="Correos de integrantes existentes",
        help_text="Separa los correos con coma o salto de línea.",
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class AgregarIntegrantesForm(forms.Form):
    correos_integrantes = forms.CharField(
        required=False,
        label="Correos de integrantes existentes",
        help_text="Separa los correos con coma o salto de línea.",
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class CompraForm(forms.Form):
    fecha = forms.DateField(
        label="Fecha",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    pagador = forms.ModelChoiceField(queryset=Usuario.objects.none(), label="Pagador")
    descripcion = forms.CharField(max_length=150, required=False, label="Descripción")
    impuesto = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        initial=0,
        label="IVA",
    )
    descuento = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        initial=0,
        label="Descuento",
    )
    total = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        label="Total declarado",
        help_text="Debe coincidir con ítems + IVA - descuento.",
    )

    def __init__(self, *args, grupo, **kwargs):
        super().__init__(*args, **kwargs)
        self.grupo = grupo
        self.fields["pagador"].queryset = integrantes_activos(grupo)
        if self.is_bound is False:
            self.fields["pagador"].initial = grupo.creador_id


class ItemForm(forms.Form):
    descripcion = forms.CharField(max_length=150, label="Ítem")
    valor = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        label="Valor",
    )
    beneficiarios = forms.ModelMultipleChoiceField(
        queryset=Usuario.objects.none(),
        label="Asignar a",
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, grupo, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["beneficiarios"].queryset = integrantes_activos(grupo)
        self.empty_permitted = True


ItemFormSet = formset_factory(ItemForm, extra=5, max_num=20, validate_max=True)


class EditarCompraForm(forms.Form):
    fecha = forms.DateField(label="Fecha", widget=forms.DateInput(attrs={"type": "date"}))
    descripcion = forms.CharField(max_length=150, required=False, label="Descripción")
    impuesto = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0, label="IVA")
    descuento = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, label="Descuento"
    )
    total = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        label="Total",
        help_text="Debe coincidir con los ítems activos + IVA - descuento.",
    )


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


class PagoForm(forms.Form):
    obligacion = forms.ModelChoiceField(queryset=Obligacion.objects.none(), label="Deuda")
    monto = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0, label="Abono")
    fecha = forms.DateField(
        label="Fecha del pago",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, grupo, deudor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["obligacion"].queryset = (
            Obligacion.objects.filter(
                grupo=grupo,
                deudor=deudor,
                anulada=False,
                asignacion__anulada=False,
                asignacion__item__anulada=False,
                asignacion__item__compra__anulada=False,
            )
            .select_related("acreedor", "asignacion__item__compra")
            .order_by("acreedor__first_name", "acreedor__last_name", "acreedor_id")
        )
        self.fields["obligacion"].label_from_instance = lambda obligation: (
            f"{obligation.acreedor} — saldo ${obligation.saldo_pendiente}"
        )
        self.deudor = deudor

    def clean(self):
        cleaned_data = super().clean()
        obligation = cleaned_data.get("obligacion")
        amount = cleaned_data.get("monto")
        if obligation and amount and amount > obligation.saldo_pendiente:
            self.add_error("monto", "El abono supera el saldo pendiente.")
        return cleaned_data


class EditarPagoForm(forms.Form):
    monto = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0, label="Monto")
    fecha = forms.DateField(label="Fecha", widget=forms.DateInput(attrs={"type": "date"}))


def integrantes_activos(grupo):
    return Usuario.objects.filter(
        Q(pk=grupo.creador_id)
        | Q(membresia__grupo=grupo, membresia__activo=True)
    ).distinct().order_by("first_name", "last_name", "email")

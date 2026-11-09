from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import Usuario
from expenses.forms import CompraForm, GrupoForm, IntegranteForm, ItemForm
from expenses.models import Compra, Grupo
from expenses.services.compras import agregar_integrante, registrar_compra, registrar_grupo
from ledger.services.saldos import calcular_saldos

FILAS_ITEMS = 5


def _grupo_del_usuario(request, grupo_id):
    """Devuelve el grupo solo si el usuario es integrante; si no, 404."""
    return get_object_or_404(Grupo, id=grupo_id, miembros__usuario=request.user)


def _miembros(grupo):
    return Usuario.objects.filter(membresia__grupo=grupo).order_by("first_name", "email")


@login_required
def lista_grupos(request):
    grupos = Grupo.objects.filter(miembros__usuario=request.user).order_by("nombre")
    return render(request, "expenses/grupos_lista.html", {"grupos": grupos})


@login_required
def crear_grupo(request):
    formulario = GrupoForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        try:
            grupo = registrar_grupo(request.user, formulario.cleaned_data["nombre"])
        except ValidationError as error:
            formulario.add_error(None, error)
        else:
            messages.success(request, "Grupo creado.")
            return redirect("grupo_detalle", grupo_id=grupo.id)
    return render(request, "expenses/grupo_form.html", {"formulario": formulario})


@login_required
def detalle_grupo(request, grupo_id):
    grupo = _grupo_del_usuario(request, grupo_id)
    miembros = _miembros(grupo)
    saldos = calcular_saldos(grupo)
    filas = [(usuario, saldos.get(usuario.id)) for usuario in miembros]
    compras = grupo.compras.select_related("pagador").order_by("-fecha", "-id")[:20]
    return render(
        request,
        "expenses/grupo_detalle.html",
        {"grupo": grupo, "filas": filas, "compras": compras},
    )


@login_required
def agregar_integrante_vista(request, grupo_id):
    grupo = _grupo_del_usuario(request, grupo_id)
    formulario = IntegranteForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        try:
            agregar_integrante(grupo, formulario.usuario, request.user)
        except ValidationError as error:
            formulario.add_error("email", error)
        else:
            messages.success(request, "Integrante agregado.")
            return redirect("grupo_detalle", grupo_id=grupo.id)
    return render(
        request, "expenses/integrante_form.html", {"grupo": grupo, "formulario": formulario}
    )


@login_required
def nueva_compra(request, grupo_id):
    grupo = _grupo_del_usuario(request, grupo_id)
    miembros = _miembros(grupo)
    ItemFormSet = forms.formset_factory(ItemForm, extra=FILAS_ITEMS)

    if request.method == "POST":
        formulario = CompraForm(request.POST, miembros=miembros)
        formset = ItemFormSet(request.POST, form_kwargs={"miembros": miembros})
        if formulario.is_valid() and formset.is_valid():
            items = [f.cleaned_data for f in formset if f.cleaned_data]
            try:
                compra = registrar_compra(
                    grupo=grupo,
                    pagador=formulario.cleaned_data["pagador"],
                    fecha=formulario.cleaned_data["fecha"],
                    descripcion=formulario.cleaned_data["descripcion"],
                    items=items,
                    registrado_por=request.user,
                )
            except ValidationError as error:
                formulario.add_error(None, error)
            else:
                messages.success(request, "Compra registrada.")
                return redirect("compra_detalle", compra_id=compra.id)
    else:
        formulario = CompraForm(miembros=miembros, initial={"pagador": request.user})
        formset = ItemFormSet(form_kwargs={"miembros": miembros})

    return render(
        request,
        "expenses/compra_form.html",
        {"grupo": grupo, "formulario": formulario, "formset": formset},
    )


@login_required
def detalle_compra(request, compra_id):
    compra = get_object_or_404(
        Compra.objects.select_related("grupo", "pagador"),
        id=compra_id,
        grupo__miembros__usuario=request.user,
    )
    items = compra.items.prefetch_related("asignaciones__beneficiario")
    return render(request, "expenses/compra_detalle.html", {"compra": compra, "items": items})

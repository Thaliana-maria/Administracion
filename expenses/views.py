from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from expenses.forms import EditarCompraForm, EditarItemForm, EditarPagoForm
from expenses.models import Compra, Grupo, Item, Membresia
from expenses.services.permisos import (
    exigir_puede_editar_compra,
    exigir_puede_editar_pago,
)
from expenses.services.reparto import repartir
from expenses.services.registros import (
    anular_compra,
    anular_item,
    actualizar_compra,
    actualizar_item,
)
from ledger.models import Pago
from ledger.services.obligaciones import anular_pago as servicio_anular_pago
from ledger.services.obligaciones import actualizar_pago


@login_required
def inicio(request):
    grupos = Grupo.objects.filter(
        Q(creador=request.user)
        | Q(miembros__usuario=request.user, miembros__activo=True)
    ).distinct()
    return render(request, "inicio.html", {"grupos": grupos})


@login_required
@require_POST
def cambiar_rol_integrante(request, grupo_id, miembro_id):
    from expenses.services.permisos import establecer_rol

    try:
        establecer_rol(request.user, grupo_id, miembro_id, request.POST.get("rol"))
    except ValidationError as error:
        for mensaje in error.messages:
            messages.error(request, mensaje)
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "El rol del integrante fue actualizado.")
    return redirect("inicio")


@login_required
@require_http_methods(["GET", "POST"])
def editar_compra(request, compra_id):
    compra = get_object_or_404(Compra.objects.select_related("grupo"), pk=compra_id)
    exigir_puede_editar_compra(compra, request.user)
    formulario = EditarCompraForm(
        request.POST or None,
        initial={
            "fecha": compra.fecha,
            "descripcion": compra.descripcion,
        },
    )
    if request.method == "POST" and formulario.is_valid():
        try:
            actualizar_compra(
                request.user,
                compra.pk,
                fecha=formulario.cleaned_data["fecha"],
                descripcion=formulario.cleaned_data["descripcion"],
            )
        except ValidationError as error:
            formulario.add_error(None, error)
        else:
            messages.success(request, "La compra fue actualizada.")
            return redirect("inicio")
    return render(
        request,
        "expenses/compra_editar.html",
        {"compra": compra, "formulario": formulario},
    )


@login_required
@require_http_methods(["GET", "POST"])
def editar_item(request, item_id):
    item = get_object_or_404(
        Item.objects.select_related("compra__grupo", "compra__pagador").prefetch_related(
            "asignaciones"
        ),
        pk=item_id,
    )
    exigir_puede_editar_compra(item.compra, request.user)
    formulario = EditarItemForm(
        request.POST or None,
        initial={
            "descripcion": item.descripcion,
            "valor": item.valor,
            "beneficiarios": [
                asignacion.beneficiario_id
                for asignacion in item.asignaciones.filter(anulada=False)
            ],
        },
        grupo=item.compra.grupo,
    )
    if request.method == "POST" and formulario.is_valid():
        try:
            reparto = repartir(
                formulario.cleaned_data["valor"],
                formulario.cleaned_data["beneficiarios"],
                pagador=item.compra.pagador_id,
            )
            actualizar_item(
                request.user,
                item.pk,
                valor=formulario.cleaned_data["valor"],
                descripcion=formulario.cleaned_data["descripcion"],
                asignaciones=reparto,
            )
        except (ValidationError, ValueError) as error:
            formulario.add_error(None, error)
        else:
            messages.success(request, "El ítem y sus asignaciones fueron actualizados.")
            return redirect("inicio")
    return render(
        request,
        "expenses/item_editar.html",
        {"item": item, "formulario": formulario},
    )


@login_required
@require_http_methods(["GET", "POST"])
def confirmar_anulacion_compra(request, compra_id):
    compra = get_object_or_404(Compra, pk=compra_id)
    exigir_puede_editar_compra(compra, request.user)
    if request.method == "POST":
        if request.POST.get("confirmar") != "si":
            return redirect("inicio")
        try:
            anular_compra(request.user, compra.pk)
        except ValidationError as error:
            for mensaje in error.messages:
                messages.error(request, mensaje)
            return render(
                request,
                "expenses/confirmar_anulacion.html",
                {"compra": compra},
                status=400,
            )
        messages.success(request, "La compra quedó anulada; los pagos e historial se conservaron.")
        return redirect("inicio")

    if compra.anulada:
        messages.error(request, "La compra ya está anulada.")
        return redirect("inicio")
    return render(request, "expenses/confirmar_anulacion.html", {"compra": compra})


@login_required
@require_POST
def anular_item_view(request, item_id):
    item = get_object_or_404(Item.objects.select_related("compra"), pk=item_id)
    try:
        anular_item(request.user, item.pk)
    except ValidationError as error:
        for mensaje in error.messages:
            messages.error(request, mensaje)
    else:
        messages.success(request, "El ítem fue anulado y su historial se conservó.")
    return redirect("inicio")


@login_required
@require_http_methods(["GET", "POST"])
def editar_pago(request, pago_id):
    pago = get_object_or_404(Pago.objects.select_related("grupo"), pk=pago_id)
    exigir_puede_editar_pago(pago, request.user)
    formulario = EditarPagoForm(
        request.POST or None,
        initial={"monto": pago.monto, "fecha": pago.fecha},
    )
    if request.method == "POST" and formulario.is_valid():
        aplicaciones = list(pago.aplicaciones.filter(anulada=False))
        monto_nuevo = formulario.cleaned_data["monto"]
        if len(aplicaciones) > 1 and monto_nuevo != pago.monto:
            formulario.add_error(
                None,
                "Para cambiar el monto de un pago aplicado a varias deudas, "
                "se necesita editar cada aplicación.",
            )
        else:
            nuevas_aplicaciones = [
                (
                    aplicacion.obligacion_id,
                    monto_nuevo if len(aplicaciones) == 1 else aplicacion.monto,
                )
                for aplicacion in aplicaciones
            ]
            try:
                actualizar_pago(
                    request.user,
                    pago.pk,
                    monto=monto_nuevo,
                    fecha=formulario.cleaned_data["fecha"],
                    aplicaciones=nuevas_aplicaciones,
                )
            except ValidationError as error:
                formulario.add_error(None, error)
            else:
                messages.success(request, "El pago fue actualizado.")
                return redirect("inicio")
    return render(
        request,
        "expenses/pago_editar.html",
        {"pago": pago, "formulario": formulario},
    )


@login_required
@require_http_methods(["GET", "POST"])
def confirmar_anulacion_pago(request, pago_id):
    pago = get_object_or_404(Pago.objects.select_related("grupo"), pk=pago_id)
    exigir_puede_editar_pago(pago, request.user)
    if request.method == "POST" and request.POST.get("confirmar") == "si":
        try:
            servicio_anular_pago(request.user, pago.pk)
        except ValidationError as error:
            for mensaje in error.messages:
                messages.error(request, mensaje)
        else:
            messages.success(request, "El pago fue anulado y quedó en el historial.")
        return redirect("inicio")
    return render(request, "expenses/confirmar_anulacion_pago.html", {"pago": pago})

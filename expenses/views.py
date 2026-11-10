from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from auditlog.services import registrar_cambio
from expenses.forms import (
    AgregarIntegrantesForm,
    CompraForm,
    EditarCompraForm,
    EditarItemForm,
    EditarPagoForm,
    GrupoForm,
    ItemFormSet,
    PagoForm,
)
from expenses.models import Compra, Grupo, Item, Membresia
from expenses.services.compras import crear_compra
from expenses.services.grupos import (
    agregar_integrantes,
    crear_grupo,
    retirar_integrante,
)
from expenses.services.permisos import (
    es_administrador,
    exigir_administrador,
    exigir_miembro,
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
from ledger.models import Obligacion, Pago
from ledger.services.obligaciones import (
    anular_pago as servicio_anular_pago,
    actualizar_pago,
    registrar_pago as servicio_registrar_pago,
)
from ledger.services.saldos import calcular_saldos
from ledger.services.simplificacion import simplificar_deudas

Usuario = get_user_model()


def _mostrar_errores(request, error):
    for mensaje in error.messages:
        messages.error(request, mensaje)


@login_required
def inicio(request):
    grupos = Grupo.objects.filter(
        Q(creador=request.user)
        | Q(miembros__usuario=request.user, miembros__activo=True)
    ).distinct()
    return render(request, "inicio.html", {"grupos": grupos})


@login_required
@require_http_methods(["GET", "POST"])
def nuevo_grupo(request):
    formulario = GrupoForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        try:
            grupo = crear_grupo(
                request.user,
                nombre=formulario.cleaned_data["nombre"],
                correos_integrantes=formulario.cleaned_data["correos_integrantes"],
            )
        except ValidationError as error:
            formulario.add_error(None, error)
        else:
            messages.success(request, "El grupo quedó creado.")
            return redirect("detalle_grupo", grupo_id=grupo.pk)
    return render(request, "expenses/grupo_form.html", {"formulario": formulario})


@login_required
def detalle_grupo(request, grupo_id):
    grupo = get_object_or_404(Grupo, pk=grupo_id)
    exigir_miembro(grupo, request.user)
    saldos = calcular_saldos(grupo)
    usuarios = Usuario.objects.in_bulk(saldos)
    resumen = [
        {"usuario": usuarios[usuario_id], "saldo": saldo}
        for usuario_id, saldo in sorted(
            saldos.items(),
            key=lambda row: (
                usuarios[row[0]].first_name.casefold(),
                usuarios[row[0]].last_name.casefold(),
                usuarios[row[0]].email.casefold(),
            ),
        )
    ]
    try:
        transferencias = simplificar_deudas(grupo)
    except ValueError as error:
        messages.error(request, str(error))
        transferencias = []
    for transferencia in transferencias:
        transferencia["deudor"] = usuarios[transferencia["deudor_id"]]
        transferencia["acreedor"] = usuarios[transferencia["acreedor_id"]]

    membresias = Membresia.objects.filter(grupo=grupo).select_related("usuario").order_by(
        "-activo", "usuario__first_name", "usuario__last_name", "usuario__email"
    )
    return render(
        request,
        "expenses/grupo_detalle.html",
        {
            "grupo": grupo,
            "resumen": resumen,
            "transferencias": transferencias,
            "membresias": membresias,
            "roles": Membresia.Rol.choices,
            "compras": grupo.compras.prefetch_related("items").order_by("-fecha", "-pk"),
            "pagos": grupo.pagos.select_related("deudor", "acreedor").order_by("-fecha", "-pk"),
            "es_administrador": es_administrador(grupo, request.user),
            "integrantes_form": AgregarIntegrantesForm(),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def integrantes_grupo(request, grupo_id):
    grupo = get_object_or_404(Grupo, pk=grupo_id)
    exigir_administrador(grupo, request.user)
    formulario = AgregarIntegrantesForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        try:
            agregados = agregar_integrantes(
                request.user,
                grupo.pk,
                formulario.cleaned_data["correos_integrantes"],
            )
        except ValidationError as error:
            formulario.add_error(None, error)
        else:
            messages.success(request, f"Integrantes agregados: {len(agregados)}.")
            return redirect("detalle_grupo", grupo_id=grupo.pk)
    return render(
        request,
        "expenses/integrantes_form.html",
        {"grupo": grupo, "formulario": formulario},
    )


@login_required
@require_POST
def retirar_integrante_grupo(request, grupo_id, miembro_id):
    grupo = get_object_or_404(Grupo, pk=grupo_id)
    try:
        retirar_integrante(request.user, grupo.pk, miembro_id)
    except ValidationError as error:
        _mostrar_errores(request, error)
    else:
        messages.success(request, "El integrante fue retirado; se conservó su historial.")
    return redirect("detalle_grupo", grupo_id=grupo.pk)


@login_required
@require_POST
def cambiar_rol_integrante(request, grupo_id, miembro_id):
    from expenses.services.permisos import establecer_rol

    grupo = get_object_or_404(Grupo, pk=grupo_id)
    try:
        establecer_rol(
            request.user,
            grupo.pk,
            miembro_id,
            request.POST.get("rol"),
        )
    except ValidationError as error:
        _mostrar_errores(request, error)
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "El rol del integrante fue actualizado.")
    return redirect("detalle_grupo", grupo_id=grupo.pk)


@login_required
@require_http_methods(["GET", "POST"])
def nueva_compra(request, grupo_id):
    grupo = get_object_or_404(Grupo, pk=grupo_id)
    exigir_miembro(grupo, request.user)
    formulario = CompraForm(request.POST or None, grupo=grupo)
    items_formset = ItemFormSet(
        request.POST or None,
        prefix="items",
        form_kwargs={"grupo": grupo},
    )
    if request.method == "POST" and formulario.is_valid() and items_formset.is_valid():
        items = []
        for form in items_formset.forms:
            if not form.cleaned_data or not form.has_changed():
                continue
            items.append(
                {
                    "descripcion": form.cleaned_data["descripcion"],
                    "valor": form.cleaned_data["valor"],
                    "beneficiarios": [
                        user.pk for user in form.cleaned_data["beneficiarios"]
                    ],
                }
            )
        try:
            compra = crear_compra(
                request.user,
                grupo.pk,
                fecha=formulario.cleaned_data["fecha"],
                pagador_id=formulario.cleaned_data["pagador"].pk,
                descripcion=formulario.cleaned_data["descripcion"],
                impuesto=formulario.cleaned_data["impuesto"],
                descuento=formulario.cleaned_data["descuento"],
                total_declarado=formulario.cleaned_data["total"],
                items=items,
            )
        except ValidationError as error:
            formulario.add_error(None, error)
        except ValueError as error:
            formulario.add_error(None, str(error))
        else:
            messages.success(request, "La compra quedó registrada y los saldos se actualizaron.")
            return redirect("detalle_grupo", grupo_id=grupo.pk)

    return render(
        request,
        "expenses/compra_form.html",
        {
            "grupo": grupo,
            "formulario": formulario,
            "items_formset": items_formset,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def editar_compra(request, compra_id):
    compra = get_object_or_404(Compra.objects.select_related("grupo"), pk=compra_id)
    exigir_puede_editar_compra(compra, request.user)
    inicial = {
        "fecha": compra.fecha,
        "descripcion": compra.descripcion,
        "impuesto": compra.impuesto,
        "descuento": compra.descuento,
        "total": compra.total,
    }
    formulario = EditarCompraForm(request.POST or None, initial=inicial)
    if request.method == "POST" and formulario.is_valid():
        try:
            actualizar_compra(
                request.user,
                compra.pk,
                fecha=formulario.cleaned_data["fecha"],
                descripcion=formulario.cleaned_data["descripcion"],
                impuesto=formulario.cleaned_data["impuesto"],
                descuento=formulario.cleaned_data["descuento"],
                total=formulario.cleaned_data["total"],
            )
        except ValidationError as error:
            formulario.add_error(None, error)
        else:
            messages.success(request, "La compra fue actualizada.")
            return redirect("detalle_grupo", grupo_id=compra.grupo_id)
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
    inicial = {
        "descripcion": item.descripcion,
        "valor": item.valor,
        "beneficiarios": [
            asignacion.beneficiario_id
            for asignacion in item.asignaciones.filter(anulada=False)
        ],
    }
    formulario = EditarItemForm(
        request.POST or None,
        initial=inicial,
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
            if isinstance(error, ValidationError):
                formulario.add_error(None, error)
            else:
                formulario.add_error(None, str(error))
        else:
            messages.success(request, "El ítem y sus asignaciones fueron actualizados.")
            return redirect("detalle_grupo", grupo_id=item.compra.grupo_id)
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
            return redirect("detalle_grupo", grupo_id=compra.grupo_id)
        try:
            anular_compra(request.user, compra.pk)
        except ValidationError as error:
            _mostrar_errores(request, error)
            return render(
                request,
                "expenses/confirmar_anulacion.html",
                {"compra": compra},
                status=400,
            )
        messages.success(request, "La compra quedó anulada; los pagos e historial se conservaron.")
        return redirect("detalle_grupo", grupo_id=compra.grupo_id)

    if compra.anulada:
        messages.error(request, "La compra ya está anulada.")
        return redirect("detalle_grupo", grupo_id=compra.grupo_id)
    return render(request, "expenses/confirmar_anulacion.html", {"compra": compra})


@login_required
@require_POST
def anular_item_view(request, item_id):
    item = get_object_or_404(Item.objects.select_related("compra__grupo"), pk=item_id)
    try:
        anular_item(request.user, item.pk)
    except ValidationError as error:
        _mostrar_errores(request, error)
    else:
        messages.success(request, "El ítem fue anulado y su historial se conservó.")
    return redirect("detalle_grupo", grupo_id=item.compra.grupo_id)


@login_required
@require_http_methods(["GET", "POST"])
def registrar_pago(request, grupo_id):
    grupo = get_object_or_404(Grupo, pk=grupo_id)
    exigir_miembro(grupo, request.user)
    formulario = PagoForm(
        request.POST or None,
        grupo=grupo,
        deudor=request.user,
    )
    if request.method == "POST" and formulario.is_valid():
        obligacion = formulario.cleaned_data["obligacion"]
        try:
            servicio_registrar_pago(
                request.user,
                grupo_id=grupo.pk,
                deudor_id=request.user.pk,
                acreedor_id=obligacion.acreedor_id,
                monto=formulario.cleaned_data["monto"],
                fecha=formulario.cleaned_data["fecha"],
                aplicaciones=[(obligacion.pk, formulario.cleaned_data["monto"])],
            )
        except ValidationError as error:
            formulario.add_error(None, error)
        else:
            messages.success(request, "El pago quedó registrado y el saldo se actualizó.")
            return redirect("detalle_grupo", grupo_id=grupo.pk)
    return render(
        request,
        "expenses/pago_form.html",
        {"grupo": grupo, "formulario": formulario},
    )


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
        try:
            if aplicaciones:
                if len(aplicaciones) > 1 and monto_nuevo != pago.monto:
                    raise ValidationError(
                        "Para cambiar el monto de un pago aplicado a varias deudas, "
                        "se necesita editar cada aplicación."
                    )
                nuevo_monto_aplicado = monto_nuevo if len(aplicaciones) == 1 else pago.monto
                nuevas_aplicaciones = [
                    (
                        aplicacion.obligacion_id,
                        nuevo_monto_aplicado
                        if len(aplicaciones) == 1
                        else aplicacion.monto,
                    )
                    for aplicacion in aplicaciones
                ]
                actualizar_pago(
                    request.user,
                    pago.pk,
                    monto=monto_nuevo,
                    fecha=formulario.cleaned_data["fecha"],
                    aplicaciones=nuevas_aplicaciones,
                )
            elif monto_nuevo != pago.monto:
                raise ValidationError(
                    "Este pago histórico no tiene aplicaciones a obligaciones; "
                    "solo se puede corregir su fecha."
                )
            else:
                datos_anteriores = {"fecha": pago.fecha.isoformat()}
                pago.fecha = formulario.cleaned_data["fecha"]
                pago.save(update_fields=["fecha"])
                registrar_cambio(
                    request.user,
                    pago,
                    "editar",
                    {
                        "antes": datos_anteriores,
                        "despues": {"fecha": pago.fecha.isoformat()},
                    },
                )
        except ValidationError as error:
            formulario.add_error(None, error)
        else:
            messages.success(request, "El pago fue actualizado.")
            return redirect("detalle_grupo", grupo_id=pago.grupo_id)
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
            _mostrar_errores(request, error)
        else:
            messages.success(request, "El pago fue anulado y quedó en el historial.")
        return redirect("detalle_grupo", grupo_id=pago.grupo_id)
    return render(request, "expenses/confirmar_anulacion_pago.html", {"pago": pago})

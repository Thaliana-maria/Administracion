from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import Usuario
from expenses.forms import (
    CompraForm,
    EditarCompraForm,
    EditarItemForm,
    EditarPagoForm,
    GrupoForm,
    IntegranteForm,
    ItemForm,
)
from expenses.models import Compra, Grupo, Item, Membresia
from expenses.services.compras import (
    agregar_integrante,
    registrar_compra,
    registrar_grupo,
)
from expenses.services.permisos import (
    exigir_miembro,
    exigir_puede_editar_compra,
    exigir_puede_editar_pago,
    es_administrador,
)
from expenses.services.reparto import repartir
from expenses.services.registros import (
    anular_compra,
    anular_item,
    actualizar_compra,
    actualizar_item,
)
from ledger.models import Pago
from ledger.services.obligaciones import (
    anular_pago as servicio_anular_pago,
    actualizar_pago,
)
from ledger.services.saldos import calcular_saldos
from ledger.services.simplificacion import simplificar_deudas


FILAS_ITEMS = 5


def _grupo_del_usuario(request, grupo_id):
    """
    Devuelve el grupo si el usuario es su creador
    o tiene una membresía activa.
    """

    return get_object_or_404(
        Grupo.objects.filter(
            Q(creador=request.user)
            | Q(
                miembros__usuario=request.user,
                miembros__activo=True,
            )
        ).distinct(),
        pk=grupo_id,
    )


def _miembros(grupo):
    """
    Obtiene los integrantes activos y garantiza que
    el creador esté incluido.
    """

    return Usuario.objects.filter(
        Q(
            membresia__grupo=grupo,
            membresia__activo=True,
        )
        | Q(pk=grupo.creador_id)
    ).distinct().order_by(
        "first_name",
        "last_name",
        "email",
    )


@login_required
def inicio(request):
    grupos = Grupo.objects.filter(
        Q(creador=request.user)
        | Q(
            miembros__usuario=request.user,
            miembros__activo=True,
        )
    ).distinct()

    return render(
        request,
        "inicio.html",
        {"grupos": grupos},
    )


@login_required
def lista_grupos(request):
    grupos = Grupo.objects.filter(
        Q(creador=request.user)
        | Q(
            miembros__usuario=request.user,
            miembros__activo=True,
        )
    ).distinct().order_by("nombre")

    return render(
        request,
        "expenses/grupos_lista.html",
        {"grupos": grupos, "formulario": GrupoForm()},
    )


@login_required
def crear_grupo(request):
    formulario = GrupoForm(request.POST or None)

    if request.method == "POST" and formulario.is_valid():
        try:
            grupo = registrar_grupo(
                request.user,
                formulario.cleaned_data["nombre"],
            )
        except ValidationError as error:
            formulario.add_error(None, error)
        else:
            messages.success(
                request,
                "Grupo creado. Ahora eres su administrador.",
            )
            return redirect(
                "grupo_detalle",
                grupo_id=grupo.id,
            )

    return render(
        request,
        "expenses/grupo_form.html",
        {"formulario": formulario},
    )


@login_required
def detalle_grupo(request, grupo_id):
    grupo = _grupo_del_usuario(request, grupo_id)

    miembros = _miembros(grupo)
    saldos = calcular_saldos(grupo)

    filas = [
        (
            usuario,
            saldos.get(usuario.id, Decimal("0.00")),
        )
        for usuario in miembros
    ]

    membresias = list(
        Membresia.objects.filter(
            grupo=grupo,
            activo=True,
        ).select_related("usuario").order_by(
            "usuario__first_name",
            "usuario__last_name",
            "usuario__email",
        )
    )

    compras = grupo.compras.select_related(
        "pagador"
    ).order_by(
        "-fecha",
        "-id",
    )[:20]

    return render(
        request,
        "expenses/grupo_detalle.html",
        {
            "grupo": grupo,
            "filas": filas,
            "compras": compras,
            "miembros": miembros,
            "membresias": membresias,
            "puede_gestionar": es_administrador(
                grupo,
                request.user,
            ),
        },
    )



@login_required
def agregar_integrante_vista(request, grupo_id):
    grupo = _grupo_del_usuario(request, grupo_id)

    if not es_administrador(grupo, request.user):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied(
            "Solo los administradores pueden agregar integrantes."
        )

    formulario = IntegranteForm(request.POST or None)

    if request.method == "POST" and formulario.is_valid():
        try:
            agregar_integrante(
                grupo,
                formulario.usuario,
                request.user,
            )
        except ValidationError as error:
            formulario.add_error("email", error)
        else:
            messages.success(
                request,
                "Integrante agregado correctamente.",
            )
            return redirect(
                "grupo_detalle",
                grupo_id=grupo.id,
            )

    return render(
        request,
        "expenses/integrante_form.html",
        {
            "grupo": grupo,
            "formulario": formulario,
        },
    )



@login_required
def nueva_compra(request, grupo_id):
    grupo = _grupo_del_usuario(request, grupo_id)
    miembros = _miembros(grupo)

    ItemFormSet = forms.formset_factory(
        ItemForm,
        extra=FILAS_ITEMS,
        max_num=100,
        validate_max=True,
        absolute_max=100,
    )

    if request.method == "POST":
        formulario = CompraForm(
            request.POST,
            miembros=miembros,
        )

        formset = ItemFormSet(
            request.POST,
            form_kwargs={"miembros": miembros},
        )

        if formulario.is_valid() and formset.is_valid():
            items = [
                form.cleaned_data
                for form in formset
                if form.cleaned_data
            ]

            try:
                compra = registrar_compra(
                    grupo=grupo,
                    pagador=formulario.cleaned_data["pagador"],
                    fecha=formulario.cleaned_data["fecha"],
                    descripcion=formulario.cleaned_data["descripcion"],
                    items=items,
                    registrado_por=request.user,
                    impuesto=formulario.cleaned_data.get("impuesto") or 0,
                    descuento=formulario.cleaned_data.get("descuento") or 0,
                    total_esperado=formulario.cleaned_data.get("total_esperado"),
                )
            except ValidationError as error:
                formulario.add_error(None, error)
            else:
                messages.success(
                    request,
                    "Compra registrada correctamente.",
                )
                return redirect(
                    "compra_detalle",
                    compra_id=compra.id,
                )

    else:
        formulario = CompraForm(
            miembros=miembros,
            initial={"pagador": request.user},
        )

        formset = ItemFormSet(
            form_kwargs={"miembros": miembros},
        )

    return render(
        request,
        "expenses/compra_form.html",
        {
            "grupo": grupo,
            "formulario": formulario,
            "formset": formset,
        },
    )


@login_required
def detalle_compra(request, compra_id):
    compra = get_object_or_404(
        Compra.objects.select_related(
            "grupo",
            "pagador",
        ),
        pk=compra_id,
    )

    exigir_miembro(
        compra.grupo_id,
        request.user,
    )

    items = compra.items.prefetch_related(
        "asignaciones__beneficiario"
    )

    return render(
        request,
        "expenses/compra_detalle.html",
        {
            "compra": compra,
            "items": items,
        },
    )



@login_required
@require_POST
def cambiar_rol_integrante(request, grupo_id, miembro_id):
    from expenses.services.permisos import establecer_rol

    try:
        establecer_rol(
            request.user,
            grupo_id,
            miembro_id,
            request.POST.get("rol"),
        )
    except ValidationError as error:
        for mensaje in error.messages:
            messages.error(request, mensaje)
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            "El rol del integrante fue actualizado correctamente.",
        )

    return redirect(
        "grupo_detalle",
        grupo_id=grupo_id,
    )


@login_required
@require_http_methods(["GET", "POST"])
def editar_compra(request, compra_id):
    compra = get_object_or_404(
        Compra.objects.select_related("grupo"),
        pk=compra_id,
    )

    exigir_puede_editar_compra(
        compra,
        request.user,
    )

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
            messages.success(
                request,
                "La compra fue actualizada.",
            )
            return redirect("inicio")

    return render(
        request,
        "expenses/compra_editar.html",
        {
            "compra": compra,
            "formulario": formulario,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def editar_item(request, item_id):
    item = get_object_or_404(
        Item.objects.select_related(
            "compra__grupo",
            "compra__pagador",
        ),
        pk=item_id,
    )

    exigir_puede_editar_compra(
        item.compra,
        request.user,
    )

    formulario = EditarItemForm(
        request.POST or None,
        initial={
            "descripcion": item.descripcion,
            "valor": item.valor,
            "beneficiarios": [
                asignacion.beneficiario_id
                for asignacion in item.asignaciones.filter(
                    anulada=False
                )
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
            messages.success(
                request,
                "El ítem y sus asignaciones fueron actualizados.",
            )
            return redirect("inicio")

    return render(
        request,
        "expenses/item_editar.html",
        {
            "item": item,
            "formulario": formulario,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def confirmar_anulacion_compra(request, compra_id):
    compra = get_object_or_404(
        Compra,
        pk=compra_id,
    )

    exigir_puede_editar_compra(
        compra,
        request.user,
    )

    if request.method == "POST":
        if request.POST.get("confirmar") != "si":
            return redirect("inicio")

        try:
            anular_compra(
                request.user,
                compra.pk,
            )
        except ValidationError as error:
            for mensaje in error.messages:
                messages.error(request, mensaje)

            return render(
                request,
                "expenses/confirmar_anulacion.html",
                {"compra": compra},
                status=400,
            )

        messages.success(
            request,
            "La compra quedó anulada; los pagos e historial se conservaron.",
        )

        return redirect("inicio")

    if compra.anulada:
        messages.error(
            request,
            "La compra ya está anulada.",
        )
        return redirect("inicio")

    return render(
        request,
        "expenses/confirmar_anulacion.html",
        {"compra": compra},
    )


@login_required
@require_POST
def anular_item_view(request, item_id):
    item = get_object_or_404(
        Item.objects.select_related("compra"),
        pk=item_id,
    )

    try:
        anular_item(
            request.user,
            item.pk,
        )
    except ValidationError as error:
        for mensaje in error.messages:
            messages.error(request, mensaje)
    else:
        messages.success(
            request,
            "El ítem fue anulado y su historial se conservó.",
        )

    return redirect("inicio")


@login_required
@require_http_methods(["GET", "POST"])
def editar_pago(request, pago_id):
    pago = get_object_or_404(
        Pago.objects.select_related("grupo"),
        pk=pago_id,
    )

    exigir_puede_editar_pago(
        pago,
        request.user,
    )

    formulario = EditarPagoForm(
        request.POST or None,
        initial={
            "monto": pago.monto,
            "fecha": pago.fecha,
        },
    )

    if request.method == "POST" and formulario.is_valid():
        aplicaciones = list(
            pago.aplicaciones.filter(anulada=False)
        )

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
                    monto_nuevo
                    if len(aplicaciones) == 1
                    else aplicacion.monto,
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
                messages.success(
                    request,
                    "El pago fue actualizado.",
                )
                return redirect("inicio")

    return render(
        request,
        "expenses/pago_editar.html",
        {
            "pago": pago,
            "formulario": formulario,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def confirmar_anulacion_pago(request, pago_id):
    pago = get_object_or_404(
        Pago.objects.select_related("grupo"),
        pk=pago_id,
    )

    exigir_puede_editar_pago(
        pago,
        request.user,
    )

    if request.method == "POST" and request.POST.get("confirmar") == "si":
        try:
            servicio_anular_pago(
                request.user,
                pago.pk,
            )
        except ValidationError as error:
            for mensaje in error.messages:
                messages.error(request, mensaje)
        else:
            messages.success(
                request,
                "El pago fue anulado y quedó en el historial.",
            )

        return redirect("inicio")

    return render(
        request,
        "expenses/confirmar_anulacion_pago.html",
        {"pago": pago},
    )


@login_required
def dashboard_grupo(request, grupo_id):
    grupo = _grupo_del_usuario(
        request,
        grupo_id,
    )

    compras_activas = Compra.objects.filter(
        grupo=grupo,
        anulada=False,
    )

    total_gastos = (
        compras_activas.aggregate(
            total=Sum("total")
        )["total"]
        or Decimal("0.00")
    )

    cantidad_items = Item.objects.filter(
        compra__grupo=grupo,
        compra__anulada=False,
        anulada=False,
    ).count()

    pagos_activos = Pago.objects.filter(
        grupo=grupo,
        anulada=False,
    )

    resumen_pagos = pagos_activos.aggregate(
        cantidad=Count("pk"),
        total=Sum("monto"),
    )
    cantidad_pagos = resumen_pagos["cantidad"]
    total_pagos = resumen_pagos["total"] or Decimal("0.00")

    saldos = calcular_saldos(grupo)

    filas_saldos = [
        (
            usuario,
            saldos.get(
                usuario.pk,
                Decimal("0.00"),
            ),
        )
        for usuario in _miembros(grupo)
    ]

    mayor_saldo = max((abs(saldo) for _, saldo in filas_saldos), default=Decimal("0"))
    barras_saldos = [(usuario, saldo, int(abs(saldo) * 100 / mayor_saldo) if mayor_saldo else 0) for usuario, saldo in filas_saldos]

    ultimas_compras = compras_activas.select_related(
        "pagador"
    ).order_by(
        "-fecha",
        "-id",
    )[:5]

    transferencias_sugeridas = []
    error_simplificacion = None

    try:
        plan = simplificar_deudas(grupo, saldos=saldos)

        ids_usuarios = {
            transferencia["deudor_id"]
            for transferencia in plan
        } | {
            transferencia["acreedor_id"]
            for transferencia in plan
        }

        usuarios = {
            usuario.pk: usuario
            for usuario, _ in filas_saldos
        }
        usuarios.update(
            Usuario.objects.in_bulk(ids_usuarios - usuarios.keys())
        )

        for transferencia in plan:
            deudor = usuarios.get(
                transferencia["deudor_id"]
            )
            acreedor = usuarios.get(
                transferencia["acreedor_id"]
            )

            if deudor is None or acreedor is None:
                continue

            transferencias_sugeridas.append(
                {
                    "deudor": deudor,
                    "acreedor": acreedor,
                    "monto": transferencia["monto"],
                }
            )

    except ValueError as error:
        error_simplificacion = str(error)

    return render(
        request,
        "expenses/grupo_dashboard.html",
        {
            "grupo": grupo,
            "total_gastos": total_gastos,
            "cantidad_items": cantidad_items,
            "cantidad_pagos": cantidad_pagos,
            "total_pagos": total_pagos,
            "cantidad_integrantes": len(filas_saldos),
            "filas_saldos": filas_saldos,
            "barras_saldos": barras_saldos,
            "ultimas_compras": ultimas_compras,
            "transferencias_sugeridas": transferencias_sugeridas,
            "error_simplificacion": error_simplificacion,
            "puede_gestionar": es_administrador(
                grupo,
                request.user,
            ),
        },
    )

@login_required
def lista_compras(request, grupo_id):
    grupo = _grupo_del_usuario(request, grupo_id)
    compras = grupo.compras.select_related("pagador").order_by("-fecha", "-id")
    pagina = Paginator(compras, 20).get_page(request.GET.get("pagina"))
    return render(request, "expenses/compras_lista.html", {"grupo": grupo, "compras": pagina})

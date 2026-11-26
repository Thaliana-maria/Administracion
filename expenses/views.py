from decimal import Decimal
from uuid import uuid4
from django.db import transaction
from expenses.models import OperacionRegistro

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import Usuario
from auditlog.models import Historial
from expenses.models import Asignacion, RevisionCompra
from auditlog.services import registrar_cambio
from django.core.exceptions import PermissionDenied
from ledger.models import Obligacion, AplicacionPago
from expenses.forms import (
    CompraForm,
    EditarCompraForm,
    EditarItemForm,
    EditarItemConjuntoForm,
    EditarPagoForm,
    GrupoForm,
    IntegranteForm,
    ItemForm,
    PagoForm,
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
    retirar_integrante,
    archivar_grupo,
)
from expenses.services.reparto import repartir
from expenses.services.registros import (
    anular_compra,
    anular_item,
    actualizar_compra,
    actualizar_item,
    actualizar_items_compra,
    version_compra,
)
from ledger.models import Pago
from ledger.services.obligaciones import (
    anular_pago as servicio_anular_pago,
    actualizar_pago,
    registrar_pago_directo,
    responder_pago,
)
from ledger.services.saldos import calcular_saldos
from ledger.services.simplificacion import simplificar_deudas, transferencias_disponibles


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
            "formulario_nombre": GrupoForm(initial={"nombre": grupo.nombre}),
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
    if grupo.archivado:
        messages.error(request, "El grupo está archivado y es de solo lectura.")
        return redirect("compras_lista", grupo_id=grupo.pk)
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
                compra = registrar_una_vez(request.user, grupo, formulario.cleaned_data["clave_operacion"], "compra", registrar_compra,
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
            initial={"pagador": request.user, "clave_operacion": uuid4()},
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
            "puede_editar": not compra.anulada and not compra.grupo.archivado and (compra.registrado_por_id == request.user.pk or es_administrador(compra.grupo, request.user)),
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

    items_activos = list(compra.items.filter(anulada=False).prefetch_related("asignaciones").order_by("pk"))
    editar_items = request.method == "POST"
    formularios_items = [
        (item, EditarItemConjuntoForm(
            request.POST if editar_items else None,
            prefix=f"item-{item.pk}",
            grupo=compra.grupo,
            initial={"descripcion": item.descripcion, "valor": item.valor,
                     "beneficiarios": [fila.beneficiario_id for fila in item.asignaciones.all() if not fila.anulada]},
        )) for item in items_activos
    ]
    formulario = EditarCompraForm(
        request.POST if editar_items else None,
        grupo=compra.grupo,
        initial={
            "fecha": compra.fecha,
            "pagador": compra.pagador_id,
            "descripcion": compra.descripcion,
            "impuesto": compra.impuesto,
            "descuento": compra.descuento,
        },
    )

    if editar_items:
        datos_validos = formulario.is_valid()
        resultados = [formulario_item.is_valid() for _, formulario_item in formularios_items]
        if datos_validos and resultados and all(resultados):
            datos = formulario.cleaned_data
            try:
                actualizar_items_compra(
                    request.user, compra.pk,
                    {item.pk: formulario_item.cleaned_data for item, formulario_item in formularios_items},
                    fecha=datos["fecha"], descripcion=datos["descripcion"],
                    pagador_id=datos["pagador"].pk if datos["pagador"] else None,
                    impuesto=datos["impuesto"] or Decimal("0"),
                    descuento=datos["descuento"] or Decimal("0"),
                    version=request.POST.get("version_compra", ""),
                )
            except ValidationError as error:
                formulario.add_error(None, error)
            else:
                messages.success(request, "La compra y sus ítems fueron actualizados.")
                return redirect("compra_detalle", compra_id=compra.pk)

    return render(
        request,
        "expenses/compra_editar.html",
        {
            "compra": compra,
            "formulario": formulario,
            "items_activos": items_activos,
            "formularios_items": formularios_items,
            "version_compra": request.POST.get("version_compra", "") if editar_items else version_compra(compra),
            "subtotal": compra.total - compra.impuesto + compra.descuento,
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

    exigir_miembro(pago.grupo, request.user)
    if pago.grupo.archivado or pago.anulada:
        raise PermissionDenied("El pago es de solo lectura.")
    if pago.estado == "confirmado":
        if request.user.pk != pago.acreedor_id:
            raise PermissionDenied("Solo el acreedor puede anular un pago confirmado.")
    else:
        exigir_puede_editar_pago(pago, request.user)

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

        return redirect("pagos_grupo", grupo_id=pago.grupo_id)

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
        estado="confirmado",
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
    pagos_disponibles = []
    error_simplificacion = None

    try:
        plan = simplificar_deudas(grupo, saldos=saldos)
        disponibles = {(fila['deudor_id'], fila['acreedor_id']): fila['monto'] for fila in transferencias_disponibles(grupo)}

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
        ids_usuarios.update(persona for pareja in disponibles for persona in pareja)
        usuarios.update(
            Usuario.objects.in_bulk(ids_usuarios - usuarios.keys())
        )
        pagos_disponibles = [
            {"deudor": usuarios[deudor], "acreedor": usuarios[acreedor], "monto": monto}
            for (deudor, acreedor), monto in disponibles.items()
            if deudor in usuarios and acreedor in usuarios
        ]

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
                    "registrable": not grupo.archivado and disponibles.get((deudor.pk, acreedor.pk), 0) >= transferencia["monto"],
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
            "pagos_disponibles": pagos_disponibles,
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


@login_required
def historial_grupo(request, grupo_id):
    grupo = _grupo_del_usuario(request, grupo_id)
    registros = [
        (("Grupo", "expenses.Grupo"), Grupo.objects.filter(pk=grupo.pk)),
        (("Membresia", "expenses.Membresia"), Membresia.objects.filter(grupo=grupo)),
        (("Compra", "expenses.Compra"), Compra.objects.filter(grupo=grupo)),
        (("Item", "expenses.Item"), Item.objects.filter(compra__grupo=grupo)),
        (("Asignacion", "expenses.Asignacion"), Asignacion.objects.filter(item__compra__grupo=grupo)),
        (("Pago", "ledger.Pago"), Pago.objects.filter(grupo=grupo)),
        (("Obligacion", "ledger.Obligacion"), Obligacion.objects.filter(grupo=grupo)),
        (("AplicacionPago", "ledger.AplicacionPago"), AplicacionPago.objects.filter(pago__grupo=grupo)),
    ]
    filtro = Q(pk__in=[])
    for tipos, objetos in registros:
        filtro |= Q(tipo_registro__in=tipos, id_registro__in=objetos.values("pk"))
    cambios = Historial.objects.filter(filtro).select_related("usuario").order_by("-fecha", "-pk")
    pagina = Paginator(cambios, 20).get_page(request.GET.get("pagina"))
    return render(request, "expenses/historial.html", {"grupo": grupo, "cambios": pagina})


@login_required
@require_http_methods(["GET", "POST"])
def pagos_grupo(request, grupo_id):
    grupo = _grupo_del_usuario(request, grupo_id)
    if grupo.archivado and request.method == "POST":
        raise PermissionDenied("El grupo está archivado.")
    formulario = PagoForm(request.POST or None, miembros=_miembros(grupo),
        usuario=request.user, administrador=es_administrador(grupo, request.user),
        initial={"deudor": request.GET.get("deudor", request.user.pk) if es_administrador(grupo, request.user) else request.user.pk, "acreedor": request.GET.get("acreedor"), "monto": request.GET.get("monto"), "clave_operacion": uuid4()})
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        try:
            registrar_una_vez(request.user, grupo, datos["clave_operacion"], "pago", registrar_pago_directo, request.user, grupo_id=grupo.pk,
                deudor_id=datos["deudor"].pk, acreedor_id=datos["acreedor"].pk,
                monto=datos["monto"], fecha=datos["fecha"])
        except ValidationError as error:
            formulario.add_error(None, error)
        else:
            messages.success(request, "Pago registrado. Espera la confirmación del acreedor.")
            return redirect("pagos_grupo", grupo_id=grupo.pk)
    pagos = grupo.pagos.select_related("deudor", "acreedor").order_by("-fecha", "-pk")
    pagina = Paginator(pagos, 20).get_page(request.GET.get("pagina"))
    return render(request, "expenses/pagos.html", {"grupo": grupo, "formulario": formulario, "pagos": pagina, "puede_gestionar": es_administrador(grupo, request.user)})


@login_required
@require_POST
def responder_pago_vista(request, grupo_id, pago_id):
    grupo = _grupo_del_usuario(request, grupo_id)
    accion = request.POST.get("accion")
    if accion not in ("confirmar", "rechazar"):
        return redirect("pagos_grupo", grupo_id=grupo.pk)
    try:
        responder_pago(request.user, grupo.pk, pago_id, accion == "confirmar")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Respuesta del pago registrada.")
    return redirect("pagos_grupo", grupo_id=grupo.pk)


@login_required
@require_POST
def retirar_integrante_vista(request, grupo_id, miembro_id):
    grupo = _grupo_del_usuario(request, grupo_id)
    try:
        retirar_integrante(request.user, grupo.pk, miembro_id)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Integrante retirado correctamente.")
        if request.user.pk == miembro_id:
            return redirect("grupos")
    return redirect("grupo_detalle", grupo_id=grupo.pk)


@login_required
@require_POST
def archivar_grupo_vista(request, grupo_id):
    grupo = _grupo_del_usuario(request, grupo_id)
    try:
        archivar_grupo(request.user, grupo.pk)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Grupo archivado. Puedes consultar su historial.")
    return redirect("grupo_detalle", grupo_id=grupo.pk)


@transaction.atomic
def registrar_una_vez(usuario, grupo_operacion, clave, tipo, servicio, *args, **datos):
    operacion, creada = OperacionRegistro.objects.get_or_create(
        clave=clave, defaults={"usuario": usuario, "grupo": grupo_operacion, "tipo": tipo}
    )
    if operacion.usuario_id != usuario.pk or operacion.grupo_id != grupo_operacion.pk or operacion.tipo != tipo:
        raise ValidationError("La clave de operación no corresponde a este registro.")
    if not creada:
        modelo = Compra if tipo == "compra" else Pago
        return modelo.objects.get(pk=operacion.registro_id, grupo=grupo_operacion)
    registro = servicio(*args, **datos)
    operacion.registro_id = registro.pk
    operacion.save(update_fields=["registro_id"])
    return registro


@login_required
@require_POST
@transaction.atomic
def responder_compra(request, compra_id):
    compra = get_object_or_404(Compra, pk=compra_id)
    grupo = _grupo_del_usuario(request, compra.grupo_id)
    grupo = Grupo.objects.select_for_update().get(pk=grupo.pk)
    compra = Compra.objects.select_for_update().get(pk=compra_id)
    exigir_miembro(grupo, request.user)
    if grupo.archivado or compra.anulada:
        raise PermissionDenied("La compra es de solo lectura.")
    revision = get_object_or_404(RevisionCompra.objects.select_for_update(), compra=compra, usuario=request.user)
    accion = request.POST.get("accion")
    if accion == "objetada" and compra.items.filter(asignaciones__obligacion__aplicaciones__anulada=False, asignaciones__obligacion__aplicaciones__pago__anulada=False, asignaciones__obligacion__aplicaciones__pago__estado="confirmado").exists():
        messages.error(request, "La compra ya tiene pagos confirmados. Consulta el historial con el grupo.")
        return redirect("compra_detalle", compra_id=compra.pk)
    if revision.estado in ("pendiente", "objetada") and accion in ("aceptada", "objetada") and revision.estado != accion:
        anterior = revision.estado
        revision.estado = accion
        revision.save(update_fields=["estado"])
        registrar_cambio(request.user, compra, "revision", {"antes": anterior, "despues": accion})
        messages.success(request, "Tu revisión fue registrada.")
    return redirect("compra_detalle", compra_id=compra.pk)


@login_required
@require_POST
@transaction.atomic
def editar_grupo(request, grupo_id):
    grupo = _grupo_del_usuario(request, grupo_id)
    grupo = Grupo.objects.select_for_update().get(pk=grupo.pk)
    if grupo.archivado or not es_administrador(grupo, request.user):
        raise PermissionDenied("No puedes editar este grupo.")
    formulario = GrupoForm(request.POST)
    if formulario.is_valid():
        nombre = formulario.cleaned_data["nombre"]
        if nombre != grupo.nombre:
            anterior = grupo.nombre
            grupo.nombre = nombre
            grupo.save(update_fields=["nombre"])
            registrar_cambio(request.user, grupo, "editar", {"antes": anterior, "despues": nombre})
        messages.success(request, "Nombre del grupo actualizado.")
    else:
        messages.error(request, "Ingresa un nombre válido de máximo 100 caracteres.")
    return redirect("grupo_detalle", grupo_id=grupo.pk)

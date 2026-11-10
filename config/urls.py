from django.urls import path, include
from accounts.views import registro
from expenses import views as expenses_views

urlpatterns = [
    path("", expenses_views.inicio, name="inicio"),
    path("registro/", registro, name="registro"),
    path("grupos/nuevo/", expenses_views.nuevo_grupo, name="nuevo_grupo"),
    path("grupos/<int:grupo_id>/", expenses_views.detalle_grupo, name="detalle_grupo"),
    path(
        "grupos/<int:grupo_id>/integrantes/",
        expenses_views.integrantes_grupo,
        name="integrantes_grupo",
    ),
    path(
        "grupos/<int:grupo_id>/integrantes/<int:miembro_id>/retirar/",
        expenses_views.retirar_integrante_grupo,
        name="retirar_integrante_grupo",
    ),
    path(
        "grupos/<int:grupo_id>/integrantes/<int:miembro_id>/rol/",
        expenses_views.cambiar_rol_integrante,
        name="cambiar_rol_integrante",
    ),
    path(
        "grupos/<int:grupo_id>/compras/nueva/",
        expenses_views.nueva_compra,
        name="nueva_compra",
    ),
    path(
        "compras/<int:compra_id>/editar/",
        expenses_views.editar_compra,
        name="editar_compra",
    ),
    path(
        "compras/<int:compra_id>/anular/",
        expenses_views.confirmar_anulacion_compra,
        name="confirmar_anulacion_compra",
    ),
    path(
        "items/<int:item_id>/editar/",
        expenses_views.editar_item,
        name="editar_item",
    ),
    path(
        "items/<int:item_id>/anular/",
        expenses_views.anular_item_view,
        name="anular_item",
    ),
    path(
        "grupos/<int:grupo_id>/pagos/nuevo/",
        expenses_views.registrar_pago,
        name="registrar_pago",
    ),
    path(
        "pagos/<int:pago_id>/editar/",
        expenses_views.editar_pago,
        name="editar_pago",
    ),
    path(
        "pagos/<int:pago_id>/anular/",
        expenses_views.confirmar_anulacion_pago,
        name="confirmar_anulacion_pago",
    ),
    path("cuentas/", include("django.contrib.auth.urls")),
]

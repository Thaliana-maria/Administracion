from django.urls import path, include
from accounts.views import registro
from expenses import views as expenses_views

urlpatterns = [
    path("", expenses_views.inicio, name="inicio"),
    path("registro/", registro, name="registro"),
    path(
        "grupos/<int:grupo_id>/integrantes/<int:miembro_id>/rol/",
        expenses_views.cambiar_rol_integrante,
        name="cambiar_rol_integrante",
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

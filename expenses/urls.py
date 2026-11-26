from django.urls import path

from expenses import views

urlpatterns = [
    path("grupos/<int:grupo_id>/archivar/", views.archivar_grupo_vista, name="archivar_grupo"),
    path("grupos/<int:grupo_id>/integrantes/<int:miembro_id>/retirar/", views.retirar_integrante_vista, name="retirar_integrante"),
    path("grupos/<int:grupo_id>/pagos/<int:pago_id>/responder/", views.responder_pago_vista, name="responder_pago"),
    path("grupos/<int:grupo_id>/pagos/", views.pagos_grupo, name="pagos_grupo"),
    path("grupos/<int:grupo_id>/cambios/", views.historial_grupo, name="historial_grupo"),
    path("grupos/", views.lista_grupos, name="grupos"),
    path("grupos/nuevo/", views.crear_grupo, name="grupo_nuevo"),
    path("grupos/<int:grupo_id>/", views.detalle_grupo, name="grupo_detalle"),
    path("grupos/<int:grupo_id>/dashboard/", views.dashboard_grupo, name="grupo_dashboard"),
    path("grupos/<int:grupo_id>/integrantes/nuevo/", views.agregar_integrante_vista, name="integrante_nuevo"),
    path("grupos/<int:grupo_id>/compras/", views.lista_compras, name="compras_lista"),
    path("grupos/<int:grupo_id>/compras/nueva/", views.nueva_compra, name="compra_nueva"),
    path("compras/<int:compra_id>/", views.detalle_compra, name="compra_detalle"),
]

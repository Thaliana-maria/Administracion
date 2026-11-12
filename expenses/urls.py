from django.urls import path

from expenses import views

urlpatterns = [
    path("grupos/", views.lista_grupos, name="grupos"),
    path("grupos/nuevo/", views.crear_grupo, name="grupo_nuevo"),
    path("grupos/<int:grupo_id>/", views.detalle_grupo, name="grupo_detalle"),
    path("grupos/<int:grupo_id>/dashboard/", views.dashboard_grupo, name="grupo_dashboard"),
    path("grupos/<int:grupo_id>/integrantes/nuevo/", views.agregar_integrante_vista, name="integrante_nuevo"),
    path("grupos/<int:grupo_id>/compras/nueva/", views.nueva_compra, name="compra_nueva"),
    path("compras/<int:compra_id>/", views.detalle_compra, name="compra_detalle"),
]

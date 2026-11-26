
from django.urls import path

from . import views

urlpatterns = [
    path("perfil/", views.editar_perfil, name="perfil"),
    path(
        "perfil/cambiar-contrasena/",
        views.cambiar_contrasena,
        name="cambiar_contrasena",
    ),
]

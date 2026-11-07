from django.urls import path, include
from django.views.generic import TemplateView
from accounts.views import registro

urlpatterns = [
    path("", TemplateView.as_view(template_name="inicio.html"), name="inicio"),
    path("registro/", registro, name="registro"),
    path("cuentas/", include("django.contrib.auth.urls")),
]

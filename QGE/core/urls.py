from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("registro/", views.register, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("grupos/", views.groups, name="groups"),
]

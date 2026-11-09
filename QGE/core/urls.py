from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("registro/", views.register, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("grupos/", views.groups, name="groups"),
    path("grupos/<int:pk>/dashboard/", views.dashboard, name="dashboard"),
    path("grupos/<int:pk>/compras/", views.expenses, name="expenses"),
    path("grupos/<int:pk>/saldos/", views.balances, name="balances"),
    path("grupos/<int:pk>/pagos/", views.payments, name="payments"),
]

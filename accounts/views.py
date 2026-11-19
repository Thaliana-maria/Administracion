
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.views.decorators.http import require_http_methods

from .forms import RegistroForm, PerfilForm


def registro(request):
    if request.method == "POST":
        formulario = RegistroForm(request.POST)
        if formulario.is_valid():
            formulario.save()
            messages.success(
                request,
                "Tu cuenta fue creada correctamente. Ya puedes iniciar sesión."
            )
            return redirect("login")
    else:
        formulario = RegistroForm()

    return render(
        request,
        "accounts/registro.html",
        {"formulario": formulario}
    )


@login_required
@require_http_methods(["GET", "POST"])
def editar_perfil(request):
    formulario = PerfilForm(
        request.POST or None,
        instance=request.user
    )

    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(
            request,
            "Tus datos personales fueron actualizados correctamente."
        )
        return redirect("perfil")

    return render(
        request,
        "accounts/perfil.html",
        {"formulario": formulario}
    )


@login_required
@require_http_methods(["GET", "POST"])
def cambiar_contrasena(request):
    formulario = PasswordChangeForm(
        user=request.user,
        data=request.POST or None
    )

    if request.method == "POST" and formulario.is_valid():
        usuario = formulario.save()
        update_session_auth_hash(request, usuario)

        messages.success(
            request,
            "Tu contraseña fue actualizada correctamente."
        )
        return redirect("perfil")

    return render(
        request,
        "accounts/cambiar_contrasena.html",
        {"formulario": formulario}
    )

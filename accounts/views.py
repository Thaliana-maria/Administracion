from django.shortcuts import render, redirect
from .forms import RegistroForm


def registro(request):
    if request.method == "POST":
        formulario = RegistroForm(request.POST)
        if formulario.is_valid():
            formulario.save()
            return redirect("login")
    else:
        formulario = RegistroForm()

    return render(request, "accounts/registro.html", {"formulario": formulario})

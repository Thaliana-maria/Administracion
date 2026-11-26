from hashlib import sha256

from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.http import HttpResponse


class InicioSesionProtegido(LoginView):
    def post(self, request, *args, **kwargs):
        direccion = request.META.get("REMOTE_ADDR", "")
        correo = request.POST.get("username", "").strip().lower()
        huella = sha256(f"{direccion}:{correo}".encode()).hexdigest()
        self.clave_intentos = f"acceso:{huella}"
        self.clave_direccion = f"acceso-ip:{sha256(direccion.encode()).hexdigest()}"
        if cache.get(self.clave_intentos, 0) >= 5 or cache.get(self.clave_direccion, 0) >= 30:
            return HttpResponse("Demasiados intentos. Intenta nuevamente en 15 minutos.", status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        for clave in (self.clave_intentos, self.clave_direccion):
            if not cache.add(clave, 1, timeout=900):
                try:
                    cache.incr(clave)
                except ValueError:
                    cache.add(clave, 1, timeout=900)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self.clave_intentos)
        return super().form_valid(form)

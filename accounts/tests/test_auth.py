
from django.test import TestCase
from django.urls import reverse
from accounts.models import Usuario


class PruebasUsuario(TestCase):
    def test_registro_de_usuario(self):
        respuesta = self.client.post(reverse("registro"), {
            "first_name": "Andres",
            "last_name": "Prueba",
            "email": "andres@example.com",
            "password1": "ClaveSegura123!",
            "password2": "ClaveSegura123!",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(Usuario.objects.filter(email="andres@example.com").exists())

    def test_contrasena_se_guarda_con_hash(self):
        usuario = Usuario.objects.create_user(
            email="prueba@example.com", password="ClaveSegura123!"
        )
        self.assertNotEqual(usuario.password, "ClaveSegura123!")
        self.assertTrue(usuario.check_password("ClaveSegura123!"))

    def test_inicio_de_sesion(self):
        Usuario.objects.create_user(
            email="login@example.com", password="ClaveSegura123!"
        )
        respuesta = self.client.post(reverse("login"), {
            "username": "login@example.com",
            "password": "ClaveSegura123!",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.wsgi_request.user.is_authenticated)

    def test_rechaza_correo_duplicado(self):
        Usuario.objects.create_user(
            email="duplicado@example.com", password="ClaveSegura123!"
        )
        respuesta = self.client.post(reverse("registro"), {
            "first_name": "Otro",
            "last_name": "Usuario",
            "email": "duplicado@example.com",
            "password1": "OtraClave123!",
            "password2": "OtraClave123!",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            Usuario.objects.filter(email="duplicado@example.com").count(), 1
        )

    def test_rechaza_contrasenas_diferentes(self):
        respuesta = self.client.post(reverse("registro"), {
            "first_name": "Andres",
            "last_name": "Prueba",
            "email": "diferente@example.com",
            "password1": "ClaveSegura123!",
            "password2": "OtraClave123!",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(
            Usuario.objects.filter(email="diferente@example.com").exists()
        )

    def test_rechaza_inicio_de_sesion_incorrecto(self):
        Usuario.objects.create_user(
            email="incorrecto@example.com", password="ClaveSegura123!"
        )
        respuesta = self.client.post(reverse("login"), {
            "username": "incorrecto@example.com",
            "password": "ClaveIncorrecta123!",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.wsgi_request.user.is_authenticated)

    def test_cierre_de_sesion(self):
        usuario = Usuario.objects.create_user(
            email="salida@example.com", password="ClaveSegura123!"
        )
        self.client.force_login(usuario)
        respuesta = self.client.post(reverse("logout"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

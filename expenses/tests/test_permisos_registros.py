from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from auditlog.models import Historial
from expenses.models import Asignacion, Compra, Grupo, Item, Membresia
from expenses.services.permisos import es_administrador, es_miembro, establecer_rol
from expenses.services.registros import actualizar_compra, actualizar_item
from ledger.models import AplicacionPago, Pago


class PruebasPermisosYRegistros(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(email="admin@test.com", password="ClaveSegura123!")
        self.pagador = Usuario.objects.create_user(
            email="pagador@test.com", password="ClaveSegura123!"
        )
        self.miembro = Usuario.objects.create_user(
            email="miembro@test.com", password="ClaveSegura123!"
        )
        self.externo = Usuario.objects.create_user(
            email="externo@test.com", password="ClaveSegura123!"
        )
        self.grupo = Grupo.objects.create(nombre="Casa", creador=self.admin)
        Membresia.objects.create(
            grupo=self.grupo,
            usuario=self.admin,
            rol=Membresia.Rol.ADMINISTRADOR,
        )
        Membresia.objects.create(grupo=self.grupo, usuario=self.pagador)
        Membresia.objects.create(grupo=self.grupo, usuario=self.miembro)
        self.compra = Compra.objects.create(
            grupo=self.grupo,
            pagador=self.pagador,
            registrado_por=self.pagador,
            fecha=date.today(),
            total=10000,
        )
        self.item = Item.objects.create(compra=self.compra, descripcion="Mercado", valor=10000)
        Asignacion.objects.create(
            item=self.item,
            beneficiario=self.pagador,
            valor_asignado=10000,
        )

    def test_solo_miembros_acceden_y_el_creador_es_administrador(self):
        self.assertTrue(es_miembro(self.grupo, self.admin))
        self.assertTrue(es_administrador(self.grupo, self.admin))
        self.assertFalse(es_miembro(self.grupo, self.externo))

    def test_administrador_asigna_rol_y_el_cambio_queda_auditado(self):
        membresia = establecer_rol(
            self.admin,
            self.grupo.pk,
            self.miembro.pk,
            Membresia.Rol.ADMINISTRADOR,
        )

        self.assertEqual(membresia.rol, Membresia.Rol.ADMINISTRADOR)
        self.assertTrue(es_administrador(self.grupo, self.miembro))
        evento = Historial.objects.get(tipo_registro="expenses.Membresia")
        self.assertEqual(evento.detalles["rol_nuevo"], Membresia.Rol.ADMINISTRADOR)

    def test_administrador_no_puede_asignar_rol_a_un_usuario_externo(self):
        with self.assertRaises(ValidationError):
            establecer_rol(
                self.admin,
                self.grupo.pk,
                self.externo.pk,
                Membresia.Rol.ADMINISTRADOR,
            )

        self.assertFalse(
            Membresia.objects.filter(
                grupo=self.grupo,
                usuario=self.externo,
            ).exists()
        )

    def test_miembro_edita_su_compra_pero_no_la_de_otro(self):
        compra = actualizar_compra(self.pagador, self.compra.pk, descripcion="Compra actualizada")
        self.assertEqual(compra.descripcion, "Compra actualizada")

        with self.assertRaises(PermissionDenied):
            actualizar_compra(self.miembro, self.compra.pk, descripcion="Cambio ajeno")

        compra = actualizar_compra(self.admin, self.compra.pk, descripcion="Cambio admin")
        self.assertEqual(compra.descripcion, "Cambio admin")
        self.assertEqual(Historial.objects.filter(accion="editar").count(), 2)

    def test_miembro_no_puede_anular_compra_ajena_y_admin_si(self):
        self.client.force_login(self.miembro)
        url = reverse("confirmar_anulacion_compra", args=[self.compra.pk])
        self.assertEqual(self.client.get(url).status_code, 403)

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_permiso_de_edicion_depende_de_quien_registro_no_del_pagador(self):
        self.compra.registrado_por = self.miembro
        self.compra.save(update_fields=["registrado_por"])

        compra = actualizar_compra(
            self.miembro,
            self.compra.pk,
            descripcion="Registrada por el miembro",
        )
        self.assertEqual(compra.descripcion, "Registrada por el miembro")

        with self.assertRaises(PermissionDenied):
            actualizar_compra(self.pagador, self.compra.pk, descripcion="Pagador")

    def test_externo_no_puede_confirmar_anulacion(self):
        self.client.force_login(self.externo)
        url = reverse("confirmar_anulacion_compra", args=[self.compra.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        respuesta = self.client.post(url, {"confirmar": "si"})

        self.assertEqual(respuesta.status_code, 403)
        self.compra.refresh_from_db()
        self.assertFalse(self.compra.anulada)

    def test_anulacion_solicita_confirmacion_y_conserva_registros(self):
        asignacion_pagador = self.item.asignaciones.get()
        asignacion_pagador.valor_asignado = 9000
        asignacion_pagador.save(update_fields=["valor_asignado"])
        asignacion_deudor = Asignacion.objects.create(
            item=self.item,
            beneficiario=self.miembro,
            valor_asignado=1000,
        )
        pago = Pago.objects.create(
            grupo=self.grupo,
            deudor=self.miembro,
            acreedor=self.pagador,
            monto=1000,
            fecha=date.today(),
        )
        aplicacion = AplicacionPago.objects.create(
            pago=pago,
            obligacion=asignacion_deudor.obligacion,
            monto=1000,
        )
        self.client.force_login(self.admin)
        url = reverse("confirmar_anulacion_compra", args=[self.compra.pk])

        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {"confirmar": "no"}).status_code, 302)
        self.compra.refresh_from_db()
        self.assertFalse(self.compra.anulada)

        respuesta = self.client.post(url, {"confirmar": "si"})
        self.assertEqual(respuesta.status_code, 302)
        self.compra.refresh_from_db()
        self.item.refresh_from_db()
        asignaciones = list(self.item.asignaciones.all())
        pago.refresh_from_db()
        self.assertTrue(self.compra.anulada)
        self.assertTrue(self.item.anulada)
        self.assertTrue(all(asignacion.anulada for asignacion in asignaciones))
        self.assertFalse(pago.anulada)
        aplicacion.refresh_from_db()
        self.assertFalse(aplicacion.anulada)
        self.assertEqual(asignaciones[0].valor_asignado + asignaciones[1].valor_asignado, 10000)
        self.assertTrue(
            Historial.objects.filter(accion="anular_por_compra").count() >= 2
        )
        self.assertEqual(Decimal(self.compra.total), Decimal("10000"))

    def test_editar_item_reemplaza_asignaciones_y_recalcula_total(self):
        anterior = self.item.asignaciones.get()

        actualizar_item(
            self.pagador,
            self.item.pk,
            valor="12000",
            descripcion="Mercado actualizado",
            asignaciones={
                self.pagador.pk: "2000",
                self.miembro.pk: "10000",
            },
        )

        self.compra.refresh_from_db()
        self.item.refresh_from_db()
        anterior.refresh_from_db()
        self.assertEqual(self.compra.total, Decimal("12000"))
        self.assertEqual(self.item.valor, Decimal("12000"))
        self.assertEqual(self.item.descripcion, "Mercado actualizado")
        self.assertTrue(anterior.anulada)
        self.assertEqual(
            self.item.asignaciones.filter(anulada=False).count(),
            2,
        )

    def test_interfaz_edita_pago_historico_y_guarda_historial(self):
        pago = Pago.objects.create(
            grupo=self.grupo,
            deudor=self.pagador,
            acreedor=self.miembro,
            monto=1000,
            fecha=date.today(),
            registrado_por=self.pagador,
        )
        self.client.force_login(self.pagador)

        respuesta = self.client.post(
            reverse("editar_pago", args=[pago.pk]),
            {"monto": "1500.00", "fecha": date.today().isoformat()},
        )

        self.assertEqual(respuesta.status_code, 302)
        pago.refresh_from_db()
        self.assertEqual(pago.monto, Decimal("1500.00"))
        self.assertEqual(pago.aplicaciones.count(), 0)
        self.assertTrue(
            Historial.objects.filter(
                tipo_registro="ledger.Pago",
                accion="editar",
            ).exists()
        )

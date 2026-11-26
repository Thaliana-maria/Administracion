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

    def test_anulacion_con_abonos_se_bloquea_y_conserva_registros(self):
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
        self.assertEqual(respuesta.status_code, 400)
        self.compra.refresh_from_db()
        self.item.refresh_from_db()
        asignaciones = list(self.item.asignaciones.all())
        pago.refresh_from_db()
        self.assertFalse(self.compra.anulada)
        self.assertFalse(self.item.anulada)
        self.assertTrue(all(not asignacion.anulada for asignacion in asignaciones))
        self.assertFalse(pago.anulada)
        aplicacion.refresh_from_db()
        self.assertFalse(aplicacion.anulada)
        self.assertEqual(asignaciones[0].valor_asignado + asignaciones[1].valor_asignado, 10000)
        self.assertTrue(
            not Historial.objects.filter(accion="anular_por_compra").exists()
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

    def test_interfaz_edita_pago_pendiente_y_guarda_historial(self):
        pago = Pago.objects.create(
            grupo=self.grupo,
            deudor=self.pagador,
            acreedor=self.miembro,
            monto=1000,
            fecha=date.today(),
            registrado_por=self.pagador,
            estado="pendiente",
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


    def test_edicion_integral_rechaza_version_desactualizada(self):
        from expenses.services.registros import actualizar_items_compra, version_compra

        version = version_compra(self.compra)
        actualizar_compra(self.pagador, self.compra.pk, descripcion="Cambio previo")
        with self.assertRaises(ValidationError):
            actualizar_items_compra(
                self.pagador, self.compra.pk,
                {self.item.pk: {"descripcion": "Mercado", "valor": Decimal("10000"),
                                "beneficiarios": [self.pagador]}},
                version=version,
            )
        self.compra.refresh_from_db()
        self.assertEqual(self.compra.descripcion, "Cambio previo")


    def test_registro_repetido_devuelve_la_misma_compra(self):
        from uuid import uuid4
        from expenses.views import registrar_una_vez
        from expenses.models import OperacionRegistro

        clave = uuid4()
        def crear():
            return Compra.objects.create(grupo=self.grupo, pagador=self.pagador,
                registrado_por=self.pagador, fecha=date.today(), total=10000)

        primera = registrar_una_vez(self.pagador, self.grupo, clave, "compra", crear)
        segunda = registrar_una_vez(self.pagador, self.grupo, clave, "compra", crear)
        self.assertEqual(primera.pk, segunda.pk)
        self.assertEqual(Compra.objects.filter(grupo=self.grupo).count(), 2)
        self.assertEqual(OperacionRegistro.objects.filter(clave=clave).count(), 1)

    def test_clave_de_operacion_no_se_comparte_entre_usuarios(self):
        from uuid import uuid4
        from expenses.views import registrar_una_vez

        clave = uuid4()
        registrar_una_vez(self.pagador, self.grupo, clave, "compra", lambda: self.compra)
        with self.assertRaises(ValidationError):
            registrar_una_vez(self.miembro, self.grupo, clave, "compra", lambda: self.compra)

    def test_operacion_fallida_no_reserva_clave(self):
        from uuid import uuid4
        from expenses.views import registrar_una_vez
        from expenses.models import OperacionRegistro

        clave = uuid4()
        def fallar():
            raise ValidationError("Compra inválida")

        with self.assertRaises(ValidationError):
            registrar_una_vez(self.pagador, self.grupo, clave, "compra", fallar)
        self.assertFalse(OperacionRegistro.objects.filter(clave=clave).exists())


    def test_retiro_con_deuda_se_bloquea(self):
        from expenses.services.permisos import retirar_integrante

        asignacion = self.item.asignaciones.get()
        asignacion.valor_asignado = 5000
        asignacion.save(update_fields=["valor_asignado"])
        Asignacion.objects.create(item=self.item, beneficiario=self.miembro, valor_asignado=5000)
        with self.assertRaises(ValidationError):
            retirar_integrante(self.admin, self.grupo.pk, self.miembro.pk)
        self.assertTrue(Membresia.objects.get(grupo=self.grupo, usuario=self.miembro).activo)

    def test_retiro_sin_deuda_conserva_membresia(self):
        from expenses.services.permisos import retirar_integrante

        membresia = retirar_integrante(self.admin, self.grupo.pk, self.miembro.pk)
        self.assertFalse(membresia.activo)
        self.assertTrue(Membresia.objects.filter(pk=membresia.pk).exists())

    def test_archivado_conserva_compras_y_bloquea_edicion(self):
        from expenses.services.permisos import archivar_grupo

        grupo = archivar_grupo(self.admin, self.grupo.pk)
        self.assertTrue(grupo.archivado)
        self.assertTrue(Compra.objects.filter(pk=self.compra.pk, anulada=False).exists())
        with self.assertRaises(PermissionDenied):
            actualizar_compra(self.pagador, self.compra.pk, descripcion="Cambio posterior")

    def test_solo_creador_puede_archivar_grupo(self):
        from expenses.services.permisos import archivar_grupo

        establecer_rol(self.admin, self.grupo.pk, self.miembro.pk, Membresia.Rol.ADMINISTRADOR)
        with self.assertRaises(PermissionDenied):
            archivar_grupo(self.miembro, self.grupo.pk)
        self.grupo.refresh_from_db()
        self.assertFalse(self.grupo.archivado)


    def test_edicion_integral_agrega_item_y_recalcula_total(self):
        from expenses.services.registros import actualizar_items_compra

        actualizar_items_compra(
            self.pagador, self.compra.pk,
            {self.item.pk: {"descripcion": "Mercado", "valor": Decimal("10000"),
                            "beneficiarios": [self.pagador]}},
            nuevos=[{"descripcion": "Aseo", "valor": Decimal("5000"),
                     "beneficiarios": [self.pagador, self.miembro]}],
            impuesto=Decimal("1000"), descuento=Decimal("500"),
        )
        self.compra.refresh_from_db()
        self.assertEqual(self.compra.total, Decimal("15500"))
        self.assertEqual(self.compra.items.filter(anulada=False).count(), 2)
        nuevo = self.compra.items.get(descripcion="Aseo")
        self.assertEqual(sum(nuevo.asignaciones.values_list("valor_asignado", flat=True)), 5000)

    def test_edicion_integral_no_permite_retirar_todos_los_items(self):
        from expenses.services.registros import actualizar_items_compra

        with self.assertRaises(ValidationError):
            actualizar_items_compra(self.pagador, self.compra.pk,
                                    {self.item.pk: {"retirar": True}})
        self.item.refresh_from_db()
        self.assertFalse(self.item.anulada)

    def test_edicion_integral_revierte_cambios_con_beneficiario_externo(self):
        from expenses.services.registros import actualizar_items_compra

        with self.assertRaises(ValidationError):
            actualizar_items_compra(
                self.pagador, self.compra.pk,
                {self.item.pk: {"descripcion": "Cambio inválido", "valor": Decimal("20000"),
                                "beneficiarios": [self.externo]}},
            )
        self.compra.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.compra.total, Decimal("10000"))
        self.assertEqual(self.item.descripcion, "Mercado")
        self.assertEqual(self.item.asignaciones.filter(anulada=False).count(), 1)

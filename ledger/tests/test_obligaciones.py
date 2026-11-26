from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from accounts.models import Usuario
from auditlog.models import Historial
from expenses.models import Asignacion, Compra, Grupo, Item, Membresia
from expenses.services.registros import anular_compra, actualizar_asignaciones
from ledger.models import AplicacionPago, Pago
from ledger.services.obligaciones import anular_pago, registrar_pago, registrar_pago_directo, responder_pago
from ledger.services.saldos import calcular_saldos


class PruebasObligacionesYPagos(TestCase):
    def setUp(self):
        self.acreedor = Usuario.objects.create_user(
            email="acreedor@test.com", password="ClaveSegura123!"
        )
        self.deudor = Usuario.objects.create_user(
            email="deudor@test.com", password="ClaveSegura123!"
        )
        self.grupo = Grupo.objects.create(nombre="Viaje", creador=self.acreedor)
        Membresia.objects.create(
            grupo=self.grupo,
            usuario=self.acreedor,
            rol=Membresia.Rol.ADMINISTRADOR,
        )
        Membresia.objects.create(grupo=self.grupo, usuario=self.deudor)
        compra = Compra.objects.create(
            grupo=self.grupo,
            pagador=self.acreedor,
            fecha=date.today(),
            total=10000,
        )
        item = Item.objects.create(compra=compra, descripcion="Hotel", valor=10000)
        Asignacion.objects.create(item=item, beneficiario=self.deudor, valor_asignado=10000)
        self.obligacion = item.asignaciones.get().obligacion
        self.compra = compra

    def registrar_abono(self, monto="2000.00", estado="confirmado"):
        return registrar_pago(
            self.deudor,
            grupo_id=self.grupo.pk,
            deudor_id=self.deudor.pk,
            acreedor_id=self.acreedor.pk,
            monto=monto,
            fecha=date.today(),
            aplicaciones=[(self.obligacion.pk, monto)],
            estado=estado,
        )

    def test_abono_queda_vinculado_y_recalcula_saldos(self):
        pago = self.registrar_abono()
        self.assertEqual(pago.aplicaciones.get().obligacion_id, self.obligacion.pk)
        self.assertEqual(self.obligacion.saldo_pendiente, Decimal("8000.00"))

        saldos = calcular_saldos(self.grupo)
        self.assertEqual(saldos[self.acreedor.pk], Decimal("8000.00"))
        self.assertEqual(saldos[self.deudor.pk], Decimal("-8000.00"))
        self.assertEqual(sum(saldos.values()), 0)

    def test_pago_no_puede_superar_el_saldo_pendiente(self):
        with self.assertRaises(ValidationError):
            self.registrar_abono("10000.01")

    def test_editar_pago_conserva_aplicaciones_anteriores(self):
        pago = self.registrar_abono(estado="pendiente")
        anterior = pago.aplicaciones.get()

        from ledger.services.obligaciones import actualizar_pago

        actualizar_pago(
            self.deudor,
            pago.pk,
            monto="2500.00",
            fecha=date.today(),
            aplicaciones=[(self.obligacion.pk, "2500.00")],
        )

        anterior.refresh_from_db()
        pago.refresh_from_db()
        self.assertTrue(anterior.anulada)
        self.assertEqual(pago.aplicaciones.filter(anulada=False).count(), 1)
        self.assertEqual(self.obligacion.saldo_pendiente, Decimal("10000.00"))
        self.assertTrue(Historial.objects.filter(tipo_registro="ledger.Pago", accion="editar").exists())

    def test_editar_pago_historico_sin_aplicaciones_conserva_y_audita(self):
        pago = Pago.objects.create(
            grupo=self.grupo,
            deudor=self.deudor,
            acreedor=self.acreedor,
            monto=100,
            fecha=date.today(),
            estado="pendiente",
        )

        from ledger.services.obligaciones import actualizar_pago

        actualizar_pago(
            self.acreedor,
            pago.pk,
            monto="150.00",
            fecha=date.today(),
            aplicaciones=[],
        )

        pago.refresh_from_db()
        self.assertEqual(pago.monto, Decimal("150.00"))
        self.assertEqual(pago.aplicaciones.count(), 0)
        self.assertTrue(Historial.objects.filter(tipo_registro="ledger.Pago", accion="editar").exists())

    def test_anulacion_de_pago_conserva_el_registro_y_restaura_la_obligacion(self):
        pago = self.registrar_abono()
        aplicacion = pago.aplicaciones.get()

        anular_pago(self.acreedor, pago.pk)
        pago.refresh_from_db()
        aplicacion.refresh_from_db()

        self.assertTrue(pago.anulada)
        self.assertFalse(aplicacion.anulada)
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(self.obligacion.saldo_pendiente, Decimal("10000.00"))
        self.assertTrue(Historial.objects.filter(tipo_registro="ledger.Pago", accion="anular").exists())

    def test_compra_con_abonos_activos_no_se_anula(self):
        pago = self.registrar_abono()
        aplicacion = pago.aplicaciones.get()

        with self.assertRaises(ValidationError):
            anular_compra(self.acreedor, self.compra.pk)

        self.compra.refresh_from_db()
        pago.refresh_from_db()
        aplicacion.refresh_from_db()
        self.assertFalse(self.compra.anulada)
        self.assertFalse(pago.anulada)
        self.assertFalse(aplicacion.anulada)
        self.assertEqual(Pago.objects.count(), 1)

    def test_editar_asignaciones_recalcula_saldos(self):
        item = self.compra.items.get()
        actualizar_asignaciones(
            self.acreedor,
            item.pk,
            {
                self.acreedor.pk: "5000",
                self.deudor.pk: "5000",
            },
        )

        saldos = calcular_saldos(self.grupo)
        self.assertEqual(saldos[self.acreedor.pk], Decimal("5000.00"))
        self.assertEqual(saldos[self.deudor.pk], Decimal("-5000.00"))
        self.assertEqual(sum(saldos.values()), 0)

    def test_anular_compra_no_elimina_pagos_no_aplicados(self):
        pago = Pago.objects.create(
            grupo=self.grupo,
            deudor=self.deudor,
            acreedor=self.acreedor,
            monto=100,
            fecha=date.today(),
        )

        anular_compra(self.acreedor, self.compra.pk)

        pago.refresh_from_db()
        self.assertFalse(pago.anulada)
        self.assertEqual(Pago.objects.count(), 1)


    def test_pago_pendiente_reserva_saldo_sin_modificarlo(self):
        pago = self.registrar_abono("8000.00", estado="pendiente")
        self.assertEqual(self.obligacion.saldo_pendiente, Decimal("10000.00"))
        with self.assertRaises(ValidationError):
            self.registrar_abono("2000.01", estado="pendiente")
        responder_pago(self.acreedor, self.grupo.pk, pago.pk, True)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, "confirmado")
        self.assertEqual(self.obligacion.saldo_pendiente, Decimal("2000.00"))

    def test_rechazo_libera_reserva_del_pago(self):
        pago = self.registrar_abono("10000.00", estado="pendiente")
        responder_pago(self.acreedor, self.grupo.pk, pago.pk, False)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, "rechazado")
        nuevo = registrar_pago_directo(
            self.deudor, grupo_id=self.grupo.pk, deudor_id=self.deudor.pk,
            acreedor_id=self.acreedor.pk, monto="10000.00", fecha=date.today(),
        )
        self.assertEqual(nuevo.estado, "pendiente")
        self.assertEqual(self.obligacion.saldo_pendiente, Decimal("10000.00"))

    def test_deudor_no_puede_confirmar_su_pago(self):
        pago = self.registrar_abono(estado="pendiente")
        with self.assertRaises(PermissionDenied):
            responder_pago(self.deudor, self.grupo.pk, pago.pk, True)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, "pendiente")

    def test_pago_no_se_confirma_dos_veces(self):
        pago = self.registrar_abono(estado="pendiente")
        responder_pago(self.acreedor, self.grupo.pk, pago.pk, True)
        with self.assertRaises(ValidationError):
            responder_pago(self.acreedor, self.grupo.pk, pago.pk, True)
        self.assertEqual(self.obligacion.saldo_pendiente, Decimal("8000.00"))


    def test_compra_objetada_no_admite_pago_directo(self):
        from expenses.models import RevisionCompra

        RevisionCompra.objects.create(compra=self.compra, usuario=self.deudor, estado="objetada")
        with self.assertRaises(ValidationError):
            registrar_pago_directo(
                self.deudor, grupo_id=self.grupo.pk, deudor_id=self.deudor.pk,
                acreedor_id=self.acreedor.pk, monto="1000.00", fecha=date.today(),
            )
        self.assertFalse(Pago.objects.filter(grupo=self.grupo).exists())

    def test_objecion_impide_confirmar_pago_pendiente(self):
        from expenses.models import RevisionCompra

        pago = self.registrar_abono(estado="pendiente")
        RevisionCompra.objects.create(compra=self.compra, usuario=self.deudor, estado="objetada")
        with self.assertRaises(ValidationError):
            responder_pago(self.acreedor, self.grupo.pk, pago.pk, True)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, "pendiente")
        self.assertEqual(self.obligacion.saldo_pendiente, Decimal("10000.00"))


    def test_saldos_conservan_participantes_historicos(self):
        Membresia.objects.filter(grupo=self.grupo, usuario=self.deudor).update(activo=False)
        saldos = calcular_saldos(self.grupo)
        self.assertEqual(saldos[self.deudor.pk], Decimal("-10000"))
        self.assertEqual(saldos[self.acreedor.pk], Decimal("10000"))
        self.assertEqual(sum(saldos.values()), 0)

    def test_saldos_incluyen_integrantes_sin_movimientos(self):
        integrante = Usuario.objects.create_user(email="nuevo@test.com", password="ClaveSegura123!")
        Membresia.objects.create(grupo=self.grupo, usuario=integrante)
        saldos = calcular_saldos(self.grupo)
        self.assertEqual(saldos[integrante.pk], Decimal("0"))
        self.assertEqual(sum(saldos.values()), 0)

    def test_calculo_saldos_utiliza_ocho_consultas(self):
        with self.assertNumQueries(8):
            saldos = calcular_saldos(self.grupo)
        self.assertEqual(sum(saldos.values()), 0)


    def test_transferencias_disponibles_respetan_reservas_y_rechazos(self):
        from ledger.services.simplificacion import transferencias_disponibles

        pago = self.registrar_abono("3000.00", estado="pendiente")
        esperado = [{"deudor_id": self.deudor.pk, "acreedor_id": self.acreedor.pk,
                     "monto": Decimal("7000")}]
        self.assertEqual(transferencias_disponibles(self.grupo), esperado)
        responder_pago(self.acreedor, self.grupo.pk, pago.pk, False)
        esperado[0]["monto"] = Decimal("10000")
        self.assertEqual(transferencias_disponibles(self.grupo), esperado)

    def test_transferencias_disponibles_excluyen_compras_objetadas(self):
        from expenses.models import RevisionCompra
        from ledger.services.simplificacion import transferencias_disponibles

        RevisionCompra.objects.create(compra=self.compra, usuario=self.deudor, estado="objetada")
        self.assertEqual(transferencias_disponibles(self.grupo), [])

    def test_transferencias_disponibles_usan_una_consulta(self):
        from ledger.services.simplificacion import transferencias_disponibles

        with self.assertNumQueries(1):
            transferencias = transferencias_disponibles(self.grupo)
        self.assertEqual(transferencias[0]["monto"], Decimal("10000"))

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import Usuario
from auditlog.models import Historial
from expenses.models import Asignacion, Compra, Grupo, Item, Membresia
from expenses.services.registros import anular_compra, actualizar_asignaciones
from ledger.models import AplicacionPago, Pago
from ledger.services.obligaciones import anular_pago, registrar_pago
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

    def registrar_abono(self, monto="2000.00"):
        return registrar_pago(
            self.deudor,
            grupo_id=self.grupo.pk,
            deudor_id=self.deudor.pk,
            acreedor_id=self.acreedor.pk,
            monto=monto,
            fecha=date.today(),
            aplicaciones=[(self.obligacion.pk, monto)],
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
        pago = self.registrar_abono()
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
        self.assertEqual(self.obligacion.saldo_pendiente, Decimal("7500.00"))
        self.assertTrue(Historial.objects.filter(tipo_registro="ledger.Pago", accion="editar").exists())

    def test_anulacion_de_pago_conserva_el_registro_y_restaura_la_obligacion(self):
        pago = self.registrar_abono()
        aplicacion = pago.aplicaciones.get()

        anular_pago(self.deudor, pago.pk)
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

        anular_compra(self.acreedor, self.compra.pk)

        self.compra.refresh_from_db()
        pago.refresh_from_db()
        aplicacion.refresh_from_db()
        self.assertTrue(self.compra.anulada)
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

from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from accounts.models import Usuario
from expenses.models import Grupo, Membresia, Compra, Item, Asignacion
from ledger.services.compensaciones import (
    solicitar_compensacion, responder_compensacion,
    confirmar_compensacion, cancelar_compensacion,
)
from ledger.services.saldos import calcular_saldos
from ledger.services.simplificacion import transferencias_disponibles


class PruebasCompensaciones(TestCase):
    def setUp(self):
        self.ana, self.beto, self.carla, self.daniel = [
            Usuario.objects.create_user(email=f"{nombre}@test.com", password="ClaveSegura123!")
            for nombre in ("ana", "beto", "carla", "daniel")
        ]
        self.grupo = Grupo.objects.create(nombre="Casa", creador=self.ana)
        for persona in (self.ana, self.beto, self.carla):
            Membresia.objects.create(grupo=self.grupo, usuario=persona)
        self.obligaciones = []
        for deudor, acreedor in ((self.ana, self.beto), (self.beto, self.carla)):
            compra = Compra.objects.create(grupo=self.grupo, pagador=acreedor, fecha=date.today(), total=10000)
            item = Item.objects.create(compra=compra, descripcion="Mercado", valor=10000)
            asignacion = Asignacion.objects.create(item=item, beneficiario=deudor, valor_asignado=10000)
            self.obligaciones.append(asignacion.obligacion)

    def solicitar(self, clave=None):
        return solicitar_compensacion(self.ana, self.grupo.pk, self.ana.pk, self.carla.pk, Decimal("10000"), clave or uuid4())

    def test_reserva_no_modifica_saldos(self):
        anterior = calcular_saldos(self.grupo)
        solicitud = self.solicitar()
        self.assertEqual(solicitud.estado, "pendiente")
        self.assertEqual(solicitud.aprobaciones.count(), 3)
        self.assertEqual(solicitud.tramos.count(), 2)
        self.assertEqual(calcular_saldos(self.grupo), anterior)
        self.assertEqual(transferencias_disponibles(self.grupo), [])

    def test_confirmacion_requiere_todas_las_aprobaciones(self):
        solicitud = self.solicitar()
        with self.assertRaises(ValidationError):
            confirmar_compensacion(self.carla, self.grupo.pk, solicitud.pk)
        for persona in (self.ana, self.beto, self.carla):
            responder_compensacion(persona, self.grupo.pk, solicitud.pk, True)
        with self.assertRaises(PermissionDenied):
            confirmar_compensacion(self.ana, self.grupo.pk, solicitud.pk)
        confirmar_compensacion(self.carla, self.grupo.pk, solicitud.pk)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, "aplicada")
        self.assertIsNotNone(solicitud.fecha_aplicacion)
        self.assertTrue(all(valor == 0 for valor in calcular_saldos(self.grupo).values()))
        for obligacion in self.obligaciones:
            self.assertEqual(obligacion.saldo_pendiente, Decimal("0"))
        confirmar_compensacion(self.carla, self.grupo.pk, solicitud.pk)
        self.assertTrue(all(valor == 0 for valor in calcular_saldos(self.grupo).values()))

    def test_rechazo_libera_reservas(self):
        solicitud = self.solicitar()
        responder_compensacion(self.beto, self.grupo.pk, solicitud.pk, False)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, "rechazada")
        self.assertEqual(len(transferencias_disponibles(self.grupo)), 2)

    def test_cancelacion_libera_reservas(self):
        solicitud = self.solicitar()
        cancelar_compensacion(self.ana, self.grupo.pk, solicitud.pk)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, "cancelada")
        self.assertEqual(len(transferencias_disponibles(self.grupo)), 2)

    def test_solicitud_repetida_no_crea_duplicados(self):
        clave = uuid4()
        primera = self.solicitar(clave)
        segunda = self.solicitar(clave)
        self.assertEqual(primera.pk, segunda.pk)
        with self.assertRaises(ValidationError):
            self.solicitar()

    def test_persona_externa_no_puede_aprobar(self):
        solicitud = self.solicitar()
        with self.assertRaises(PermissionDenied):
            responder_compensacion(self.daniel, self.grupo.pk, solicitud.pk, True)

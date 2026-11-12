from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounts.models import Usuario
from expenses.models import Grupo, Membresia, Compra, Item, Asignacion
from expenses.services.reparto import repartir
from ledger.services.saldos import calcular_saldos
from ledger.models import Pago


class PruebasSaldos(TestCase):

    def test_ca14_reparto_y_saldos_del_grupo_suman_cero(self):
        personas = [
            Usuario.objects.create_user(
                email=f"ca14-{n}@test.com",
                password="ClaveSegura123!"
            )
            for n in range(3)
        ]

        grupo = Grupo.objects.create(
            nombre="CA-14",
            creador=personas[0]
        )

        for persona in personas:
            Membresia.objects.create(
                grupo=grupo,
                usuario=persona
            )

        compra = Compra.objects.create(
            grupo=grupo,
            pagador=personas[0],
            fecha=date.today(),
            total=10000
        )

        item = Item.objects.create(
            compra=compra,
            descripcion="Ítem",
            valor=10000
        )

        reparto = repartir(
            10000,
            [
                {"id": personas[0].pk, "nombre": "Andrés"},
                {"id": personas[1].pk, "nombre": "Beatriz"},
                {"id": personas[2].pk, "nombre": "Carlos"},
            ],
            pagador=personas[0].pk,
        )

        for persona in personas:
            Asignacion.objects.create(
                item=item,
                beneficiario=persona,
                valor_asignado=reparto[persona.pk],
            )

        self.assertEqual(
            [reparto[persona.pk] for persona in personas],
            [Decimal("3334"), Decimal("3333"), Decimal("3333")],
        )

        saldos = calcular_saldos(grupo)

        self.assertEqual(
            sum(reparto.values()),
            Decimal("10000")
        )
        self.assertEqual(sum(saldos.values()), 0)

    def test_calcula_saldos_y_balance_cero(self):
        andres = Usuario.objects.create_user(
            email="andres@test.com",
            password="Clave12345"
        )

        beatriz = Usuario.objects.create_user(
            email="beatriz@test.com",
            password="Clave12345"
        )

        grupo = Grupo.objects.create(
            nombre="Casa",
            creador=andres
        )

        Membresia.objects.create(grupo=grupo, usuario=andres)
        Membresia.objects.create(grupo=grupo, usuario=beatriz)

        compra = Compra.objects.create(
            grupo=grupo,
            pagador=andres,
            fecha=date.today(),
            total=10000
        )

        item = Item.objects.create(
            compra=compra,
            descripcion="Mercado",
            valor=10000
        )

        Asignacion.objects.create(
            item=item,
            beneficiario=andres,
            valor_asignado=5000
        )

        Asignacion.objects.create(
            item=item,
            beneficiario=beatriz,
            valor_asignado=5000
        )

        saldos = calcular_saldos(grupo)

        self.assertEqual(saldos[andres.id], 5000)
        self.assertEqual(saldos[beatriz.id], -5000)
        self.assertEqual(sum(saldos.values()), 0)

    def test_consultas_de_saldos_no_aumentan_por_cada_integrante(self):
        andres = Usuario.objects.create_user(
            email="andres2@test.com",
            password="Clave12345"
        )

        grupo = Grupo.objects.create(
            nombre="Grupo grande",
            creador=andres
        )

        Membresia.objects.create(grupo=grupo, usuario=andres)

        for numero in range(9):
            usuario = Usuario.objects.create_user(
                email=f"persona{numero}@test.com",
                password="Clave12345"
            )

            Membresia.objects.create(
                grupo=grupo,
                usuario=usuario
            )

        with self.assertNumQueries(6):
            saldos = calcular_saldos(grupo)

        self.assertEqual(len(saldos), 10)

    def test_pago_reduce_la_deuda_y_el_saldo_del_acreedor(self):
        andres = Usuario.objects.create_user(
            email="andres_pago@test.com",
            password="Clave12345"
        )

        beatriz = Usuario.objects.create_user(
            email="beatriz_pago@test.com",
            password="Clave12345"
        )

        grupo = Grupo.objects.create(
            nombre="Pago de prueba",
            creador=andres
        )

        Membresia.objects.create(grupo=grupo, usuario=andres)
        Membresia.objects.create(grupo=grupo, usuario=beatriz)

        compra = Compra.objects.create(
            grupo=grupo,
            pagador=andres,
            fecha=date.today(),
            total=10000
        )

        item = Item.objects.create(
            compra=compra,
            descripcion="Mercado",
            valor=10000
        )

        Asignacion.objects.create(
            item=item,
            beneficiario=andres,
            valor_asignado=5000
        )

        Asignacion.objects.create(
            item=item,
            beneficiario=beatriz,
            valor_asignado=5000
        )

        Pago.objects.create(
            grupo=grupo,
            deudor=beatriz,
            acreedor=andres,
            monto=2000,
            fecha=date.today(),
        )

        saldos = calcular_saldos(grupo)

        self.assertEqual(saldos[andres.id], 3000)
        self.assertEqual(saldos[beatriz.id], -3000)
        self.assertEqual(sum(saldos.values()), 0)
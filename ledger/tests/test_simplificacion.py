from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from accounts.models import Usuario
from expenses.models import Asignacion, Compra, Grupo, Item, Membresia
from ledger.services.simplificacion import simplificar_deudas


class PruebasSimplificacion(SimpleTestCase):
    @patch(
        "ledger.services.simplificacion.calcular_saldos",
        return_value={1: Decimal("-6.00"), 2: Decimal("4.00"), 3: Decimal("6.00"), 4: Decimal("-4.00")},
    )
    def test_encuentra_el_minimo_de_transferencias(self, calcular):
        plan = simplificar_deudas(1)

        self.assertEqual(len(plan), 2)
        self.assertEqual(
            {(pago["deudor_id"], pago["acreedor_id"], pago["monto"]) for pago in plan},
            {(1, 3, Decimal("6")), (4, 2, Decimal("4"))},
        )

    @patch(
        "ledger.services.simplificacion.calcular_saldos",
        return_value={1: Decimal("-10.00"), 2: Decimal("0.00"), 3: Decimal("10.00")},
    )
    def test_devuelve_una_transferencia_por_el_saldo_neto(self, calcular):
        plan = simplificar_deudas(1)
        self.assertEqual(plan[0]["monto"], Decimal("10"))

    @patch(
        "ledger.services.simplificacion.calcular_saldos",
        return_value={1: Decimal("-10.00"), 2: Decimal("1.00"), 3: Decimal("10.00")},
    )
    def test_informa_si_los_saldos_no_suman_cero(self, calcular):
        with self.assertRaises(ValueError):
            simplificar_deudas(1)


class PruebasCasoAceptacionCruceDeudas(TestCase):
    def test_cadena_a_b_c_se_sugiere_como_transferencia_a_c(self):
        persona_a = Usuario.objects.create_user(email="a@test.com", password="ClaveSegura123!")
        persona_b = Usuario.objects.create_user(email="b@test.com", password="ClaveSegura123!")
        persona_c = Usuario.objects.create_user(email="c@test.com", password="ClaveSegura123!")
        grupo = Grupo.objects.create(nombre="Cadena", creador=persona_c)
        for usuario in (persona_a, persona_b, persona_c):
            Membresia.objects.create(grupo=grupo, usuario=usuario)

        compra_b = Compra.objects.create(
            grupo=grupo, pagador=persona_b, fecha="2026-11-10", total=10000
        )
        item_b = Item.objects.create(compra=compra_b, descripcion="A-B", valor=10000)
        Asignacion.objects.create(item=item_b, beneficiario=persona_a, valor_asignado=10000)

        compra_c = Compra.objects.create(
            grupo=grupo, pagador=persona_c, fecha="2026-11-10", total=10000
        )
        item_c = Item.objects.create(compra=compra_c, descripcion="B-C", valor=10000)
        Asignacion.objects.create(item=item_c, beneficiario=persona_b, valor_asignado=10000)

        plan = simplificar_deudas(grupo)

        self.assertEqual(
            plan,
            [{"deudor_id": persona_a.pk, "acreedor_id": persona_c.pk, "monto": Decimal("10000")}],
        )

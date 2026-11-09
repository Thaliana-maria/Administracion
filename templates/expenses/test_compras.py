from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import Usuario
from auditlog.models import Historial
from expenses.models import Asignacion, Compra, Grupo, Item, Membresia
from expenses.services.compras import (
    agregar_integrante,
    registrar_compra,
    registrar_grupo,
    validar_items,
)


def crear_usuario(email):
    return Usuario.objects.create_user(email=email, password="clave12345")


class BaseCompras(TestCase):
    def setUp(self):
        self.ana = crear_usuario("ana@test.com")
        self.luis = crear_usuario("luis@test.com")
        self.sara = crear_usuario("sara@test.com")
        self.afuera = crear_usuario("afuera@test.com")

        self.grupo = registrar_grupo(self.ana, "Apartamento")
        agregar_integrante(self.grupo, self.luis, self.ana)
        agregar_integrante(self.grupo, self.sara, self.ana)


class GrupoTests(TestCase):
    def setUp(self):
        self.ana = crear_usuario("ana@test.com")
        self.luis = crear_usuario("luis@test.com")

    def test_registrar_grupo_deja_al_creador_como_integrante(self):
        grupo = registrar_grupo(self.ana, "  Casa  ")
        self.assertEqual(grupo.nombre, "Casa")
        self.assertTrue(Membresia.objects.filter(grupo=grupo, usuario=self.ana).exists())

    def test_registrar_grupo_guarda_historial(self):
        grupo = registrar_grupo(self.ana, "Casa")
        self.assertTrue(
            Historial.objects.filter(
                tipo_registro="Grupo", id_registro=grupo.id, accion="crear"
            ).exists()
        )

    def test_nombre_vacio_no_se_permite(self):
        with self.assertRaises(ValidationError):
            registrar_grupo(self.ana, "   ")
        self.assertEqual(Grupo.objects.count(), 0)

    def test_agregar_integrante(self):
        grupo = registrar_grupo(self.ana, "Casa")
        agregar_integrante(grupo, self.luis, self.ana)
        self.assertTrue(Membresia.objects.filter(grupo=grupo, usuario=self.luis).exists())

    def test_no_se_puede_agregar_dos_veces(self):
        grupo = registrar_grupo(self.ana, "Casa")
        agregar_integrante(grupo, self.luis, self.ana)
        with self.assertRaises(ValidationError):
            agregar_integrante(grupo, self.luis, self.ana)

    def test_solo_un_integrante_puede_agregar_personas(self):
        grupo = registrar_grupo(self.ana, "Casa")
        with self.assertRaises(ValidationError):
            agregar_integrante(grupo, self.ana, self.luis)


class ValidarItemsTests(BaseCompras):
    def test_sin_items(self):
        with self.assertRaises(ValidationError):
            validar_items(self.grupo, [])

    def test_descripcion_obligatoria(self):
        with self.assertRaises(ValidationError):
            validar_items(self.grupo, [{"descripcion": " ", "valor": 1000}])

    def test_valor_cero(self):
        with self.assertRaises(ValidationError):
            validar_items(self.grupo, [{"descripcion": "Arroz", "valor": 0}])

    def test_valor_negativo(self):
        with self.assertRaises(ValidationError):
            validar_items(self.grupo, [{"descripcion": "Arroz", "valor": -500}])

    def test_valor_con_decimales(self):
        with self.assertRaises(ValidationError):
            validar_items(self.grupo, [{"descripcion": "Arroz", "valor": "10.5"}])

    def test_valor_no_numerico(self):
        with self.assertRaises(ValidationError):
            validar_items(self.grupo, [{"descripcion": "Arroz", "valor": "abc"}])

    def test_destino_invalido(self):
        with self.assertRaises(ValidationError):
            validar_items(
                self.grupo, [{"descripcion": "Arroz", "valor": 1000, "destino": "vecino"}]
            )

    def test_persona_sin_beneficiario(self):
        with self.assertRaises(ValidationError):
            validar_items(
                self.grupo, [{"descripcion": "Arroz", "valor": 1000, "destino": "persona"}]
            )

    def test_beneficiario_fuera_del_grupo(self):
        with self.assertRaises(ValidationError):
            validar_items(
                self.grupo,
                [
                    {
                        "descripcion": "Arroz",
                        "valor": 1000,
                        "destino": "persona",
                        "beneficiario": self.afuera.id,
                    }
                ],
            )

    def test_items_validos_se_normalizan(self):
        normalizados, miembros = validar_items(
            self.grupo,
            [
                {"descripcion": " Arroz ", "valor": "3000"},
                {
                    "descripcion": "Jabón",
                    "valor": 2000,
                    "destino": "persona",
                    "beneficiario": self.luis,
                },
            ],
        )
        self.assertEqual(normalizados[0]["descripcion"], "Arroz")
        self.assertEqual(normalizados[0]["destino"], "todos")
        self.assertEqual(normalizados[0]["valor"], Decimal("3000"))
        self.assertEqual(normalizados[1]["beneficiario"], self.luis)
        self.assertEqual(len(miembros), 3)


class RegistrarCompraTests(BaseCompras):
    def test_total_es_la_suma_de_los_items(self):
        compra = registrar_compra(
            self.grupo,
            self.ana,
            date(2026, 11, 8),
            "Mercado",
            [
                {"descripcion": "Arroz", "valor": 3000},
                {"descripcion": "Leche", "valor": 7000},
            ],
        )
        self.assertEqual(compra.total, Decimal("10000"))
        self.assertEqual(compra.items.count(), 2)

    def test_item_para_una_persona_va_completo_a_ella(self):
        compra = registrar_compra(
            self.grupo,
            self.ana,
            date(2026, 11, 8),
            "",
            [
                {
                    "descripcion": "Jabón",
                    "valor": 5000,
                    "destino": "persona",
                    "beneficiario": self.luis.id,
                }
            ],
        )
        asignaciones = Asignacion.objects.filter(item__compra=compra)
        self.assertEqual(asignaciones.count(), 1)
        self.assertEqual(asignaciones.first().beneficiario, self.luis)
        self.assertEqual(asignaciones.first().valor_asignado, Decimal("5000"))

    def test_item_para_todos_reparte_el_valor_completo(self):
        compra = registrar_compra(
            self.grupo,
            self.ana,
            date(2026, 11, 8),
            "",
            [{"descripcion": "Arroz", "valor": 10000, "destino": "todos"}],
        )
        asignaciones = Asignacion.objects.filter(item__compra=compra)
        suma = sum(a.valor_asignado for a in asignaciones)
        self.assertEqual(suma, Decimal("10000"))
        self.assertTrue(all(a.valor_asignado > 0 for a in asignaciones))

    def test_item_de_mascota_se_marca_y_se_reparte_como_todos(self):
        compra = registrar_compra(
            self.grupo,
            self.ana,
            date(2026, 11, 8),
            "",
            [{"descripcion": "Concentrado", "valor": 9000, "destino": "mascota"}],
        )
        item = Item.objects.get(compra=compra)
        self.assertEqual(item.descripcion, "Concentrado (mascota)")
        suma = sum(a.valor_asignado for a in item.asignaciones.all())
        self.assertEqual(suma, Decimal("9000"))

    def test_pagador_debe_ser_integrante(self):
        with self.assertRaises(ValidationError):
            registrar_compra(
                self.grupo,
                self.afuera,
                date(2026, 11, 8),
                "",
                [{"descripcion": "Arroz", "valor": 1000}],
                registrado_por=self.ana,
            )

    def test_quien_registra_debe_ser_integrante(self):
        with self.assertRaises(ValidationError):
            registrar_compra(
                self.grupo,
                self.ana,
                date(2026, 11, 8),
                "",
                [{"descripcion": "Arroz", "valor": 1000}],
                registrado_por=self.afuera,
            )

    def test_si_un_item_es_invalido_no_se_guarda_nada(self):
        with self.assertRaises(ValidationError):
            registrar_compra(
                self.grupo,
                self.ana,
                date(2026, 11, 8),
                "",
                [
                    {"descripcion": "Arroz", "valor": 3000},
                    {"descripcion": "Leche", "valor": 0},
                ],
            )
        self.assertEqual(Compra.objects.count(), 0)
        self.assertEqual(Item.objects.count(), 0)

    def test_registrar_compra_guarda_historial(self):
        compra = registrar_compra(
            self.grupo,
            self.ana,
            date(2026, 11, 8),
            "",
            [{"descripcion": "Arroz", "valor": 1000}],
        )
        self.assertTrue(
            Historial.objects.filter(
                tipo_registro="Compra", id_registro=compra.id, accion="crear"
            ).exists()
        )
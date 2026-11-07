from django.test import SimpleTestCase
from expenses.services.reparto import repartir


class PruebasReparto(SimpleTestCase):
    def setUp(self):
        self.personas = [
            {"id": 1, "nombre": "Andres"},
            {"id": 2, "nombre": "Beatriz"},
            {"id": 3, "nombre": "Carlos"},
        ]

    def test_reparte_el_valor(self):
        resultado = repartir(30000, self.personas)
        self.assertEqual(sum(resultado.values()), 30000)
        self.assertEqual(list(resultado.values()), [10000, 10000, 10000])

    def test_aplica_redondeo_rn05_al_pagador(self):
        resultado = repartir(10000, self.personas, pagador=3)
        self.assertEqual(resultado[3], 3334)
        self.assertEqual(resultado[1], 3333)
        self.assertEqual(resultado[2], 3333)

    def test_rechaza_valor_no_valido(self):
        with self.assertRaises(ValueError):
            repartir(0, self.personas)

    def test_rechaza_lista_vacia(self):
        with self.assertRaises(ValueError):
            repartir(1000, [])

    
    def test_rechaza_valores_con_decimales(self):
        with self.assertRaises(ValueError):
            repartir(10000.50, self.personas)

    def test_rechaza_beneficiarios_repetidos(self):
        personas_repetidas = [
            {"id": 1, "nombre": "Andres"},
            {"id": 1, "nombre": "Andres"},
        ]
        with self.assertRaises(ValueError):
            repartir(10000, personas_repetidas)

    def test_reparte_sobrante_por_orden_alfabetico(self):
        personas = [
            {"id": 3, "nombre": "Carlos"},
            {"id": 2, "nombre": "Beatriz"},
            {"id": 1, "nombre": "Andres"},
        ]
        resultado = repartir(10000, personas)

        self.assertEqual(resultado[1], 3334)
        self.assertEqual(resultado[2], 3333)
        self.assertEqual(resultado[3], 3333)

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


    def test_rechaza_valores_no_finitos_y_texto(self):
        for valor in ("NaN", "Infinity", "-Infinity", "texto", None):
            with self.subTest(valor=valor):
                with self.assertRaises(ValueError):
                    repartir(valor, self.personas)

    def test_desempata_nombres_iguales_por_identificador(self):
        personas = [{"id": 9, "nombre": "Juan"}, {"id": 2, "nombre": "Juan"}]
        esperado = {2: 6, 9: 5}
        self.assertEqual(repartir(11, personas), esperado)
        self.assertEqual(repartir(11, list(reversed(personas))), esperado)

    def test_prioridad_del_pagador_con_nombres_iguales(self):
        personas = [{"id": 9, "nombre": "Juan"}, {"id": 2, "nombre": "Juan"}]
        self.assertEqual(repartir(11, personas, pagador=9), {2: 5, 9: 6})

    def test_conserva_total_en_distintos_repartos(self):
        for valor in (3, 4, 5, 100003, 9999999999):
            for pagador in (None, 1, 2, 3):
                with self.subTest(valor=valor, pagador=pagador):
                    resultado = repartir(valor, self.personas, pagador=pagador)
                    self.assertEqual(sum(resultado.values()), valor)
                    self.assertLessEqual(max(resultado.values()) - min(resultado.values()), 1)

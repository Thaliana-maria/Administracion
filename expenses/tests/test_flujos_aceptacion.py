import time
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from auditlog.models import Historial
from expenses.models import AjusteCompra, Compra, Grupo, Membresia
from expenses.services.compras import crear_compra
from expenses.services.grupos import agregar_integrantes, crear_grupo, retirar_integrante
from ledger.models import Pago
from ledger.services.saldos import calcular_saldos


class PruebasFlujosDeAceptacion(TestCase):
    def crear_compra(self, *, item_value="30000", total=None, beneficiaries=None, **extra):
        grupo = extra.pop("grupo", self.grupo)
        beneficiaries = beneficiaries or [self.admin.pk, self.b.pk, self.c.pk]
        item_value = Decimal(item_value)
        return crear_compra(
            self.admin,
            grupo.pk,
            fecha=date(2026, 11, 10),
            pagador_id=extra.pop("pagador_id", self.admin.pk),
            descripcion="Mercado",
            impuesto=extra.pop("impuesto", "0"),
            descuento=extra.pop("descuento", "0"),
            total_declarado=total if total is not None else item_value,
            items=[
                {
                    "descripcion": "Ítem",
                    "valor": item_value,
                    "beneficiarios": beneficiaries,
                }
            ],
        )

    def setUp(self):
        self.admin = Usuario.objects.create_user(
            email="admin-flujos@test.com",
            password="ClaveSegura123!",
            first_name="Ana",
        )
        self.b = Usuario.objects.create_user(
            email="b-flujos@test.com",
            password="ClaveSegura123!",
            first_name="Beatriz",
        )
        self.c = Usuario.objects.create_user(
            email="c-flujos@test.com",
            password="ClaveSegura123!",
            first_name="Carlos",
        )
        self.grupo = crear_grupo(
            self.admin,
            nombre="Casa compartida",
            correos_integrantes="b-flujos@test.com, c-flujos@test.com",
        )

    def test_ca01_crea_grupo_y_muestra_integrantes(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("detalle_grupo", args=[self.grupo.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ana")
        self.assertContains(respuesta, "Beatriz")
        self.assertContains(respuesta, "Carlos")
        self.assertEqual(Membresia.objects.filter(grupo=self.grupo, activo=True).count(), 3)

    def test_usuario_crea_grupo_desde_la_interfaz(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(
            reverse("nuevo_grupo"),
            {
                "nombre": "Nuevo grupo",
                "correos_integrantes": "b-flujos@test.com",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        grupo = Grupo.objects.get(nombre="Nuevo grupo")
        self.assertTrue(
            Membresia.objects.filter(
                grupo=grupo,
                usuario=self.admin,
                rol=Membresia.Rol.ADMINISTRADOR,
            ).exists()
        )
        self.assertTrue(Membresia.objects.filter(grupo=grupo, usuario=self.b).exists())

    def test_admin_agrega_y_retira_integrante_sin_borrar_historial(self):
        nuevo = Usuario.objects.create_user(
            email="nuevo-flujos@test.com",
            password="ClaveSegura123!",
        )
        agregados = agregar_integrantes(
            self.admin,
            self.grupo.pk,
            nuevo.email,
        )
        self.assertEqual(agregados, [nuevo.pk])

        membresia = retirar_integrante(self.admin, self.grupo.pk, nuevo.pk)
        self.assertFalse(membresia.activo)
        self.assertFalse(
            Membresia.objects.filter(
                grupo=self.grupo,
                usuario=nuevo,
                activo=True,
            ).exists()
        )
        self.assertTrue(Historial.objects.filter(accion="retirar_integrante").exists())

    def test_ca02_y_ca03_registra_compra_y_asigna_partes_iguales(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(
            reverse("nueva_compra", args=[self.grupo.pk]),
            {
                "fecha": "2026-11-10",
                "pagador": self.admin.pk,
                "descripcion": "Compra del mes",
                "impuesto": "0",
                "descuento": "0",
                "total": "30000",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "20",
                "items-0-descripcion": "Mercado",
                "items-0-valor": "30000",
                "items-0-beneficiarios": [
                    str(self.admin.pk),
                    str(self.b.pk),
                    str(self.c.pk),
                ],
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        compra = Compra.objects.get(grupo=self.grupo)
        self.assertEqual(compra.total, Decimal("30000"))
        self.assertEqual(compra.items.get().asignaciones.count(), 3)
        self.assertEqual(
            set(compra.items.get().asignaciones.values_list("valor_asignado", flat=True)),
            {Decimal("10000")},
        )
        self.assertTrue(Historial.objects.filter(tipo_registro="expenses.Compra", accion="crear").exists())
        detalle = self.client.get(reverse("detalle_grupo", args=[self.grupo.pk]))
        self.assertContains(detalle, "Compra del mes")

    def test_ca04_pago_parcial_reduce_saldo_y_guarda_historial(self):
        compra = self.crear_compra(item_value="30000", beneficiaries=[self.admin.pk, self.b.pk])
        obligacion = compra.items.get().asignaciones.get(beneficiario=self.b).obligacion
        self.client.force_login(self.b)
        respuesta = self.client.post(
            reverse("registrar_pago", args=[self.grupo.pk]),
            {
                "obligacion": obligacion.pk,
                "monto": "2500",
                "fecha": "2026-11-10",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        pago = Pago.objects.get(grupo=self.grupo)
        self.assertEqual(pago.monto, Decimal("2500"))
        self.assertEqual(obligacion.saldo_pendiente, Decimal("12500"))
        self.assertTrue(Historial.objects.filter(tipo_registro="ledger.Pago", accion="registrar").exists())

    def test_ca05_rechaza_compra_con_campo_vacio_o_valor_negativo(self):
        self.client.force_login(self.admin)
        url = reverse("nueva_compra", args=[self.grupo.pk])
        base = {
            "fecha": "2026-11-10",
            "pagador": self.admin.pk,
            "descripcion": "Compra inválida",
            "impuesto": "0",
            "descuento": "0",
            "total": "1000",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "20",
            "items-0-descripcion": "Producto",
            "items-0-valor": "-1000",
            "items-0-beneficiarios": [str(self.admin.pk)],
        }

        respuesta = self.client.post(url, base)
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Compra.objects.filter(grupo=self.grupo).exists())
        self.assertTrue(respuesta.context["items_formset"].forms[0].errors)

        vacia = dict(base, **{"items-0-valor": "", "items-0-descripcion": ""})
        respuesta = self.client.post(url, vacia)
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Compra.objects.filter(grupo=self.grupo).exists())
        self.assertTrue(respuesta.context["items_formset"].forms[0].errors)

    def test_ca06_registro_compra_y_resumen_duran_menos_de_dos_segundos(self):
        self.client.force_login(self.admin)
        inicio = time.perf_counter()
        respuesta = self.client.post(
            reverse("nueva_compra", args=[self.grupo.pk]),
            {
                "fecha": "2026-11-10",
                "pagador": self.admin.pk,
                "descripcion": "Rendimiento",
                "impuesto": "0",
                "descuento": "0",
                "total": "10000",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "20",
                "items-0-descripcion": "Producto",
                "items-0-valor": "10000",
                "items-0-beneficiarios": [str(self.admin.pk), str(self.b.pk)],
            },
        )
        respuesta_resumen = self.client.get(reverse("detalle_grupo", args=[self.grupo.pk]))
        elapsed = time.perf_counter() - inicio

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta_resumen.status_code, 200)
        self.assertLess(elapsed, 2.0)

    def test_ca07_muestra_saldos_correctos_en_resumen(self):
        self.crear_compra(item_value="30000")
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("detalle_grupo", args=[self.grupo.pk]))

        self.assertContains(respuesta, "A favor: $20000,00")
        self.assertContains(respuesta, "Debe: $10000.00")
        saldos = calcular_saldos(self.grupo)
        self.assertEqual(saldos[self.admin.pk], Decimal("20000"))
        self.assertEqual(saldos[self.b.pk], Decimal("-10000"))
        self.assertEqual(saldos[self.c.pk], Decimal("-10000"))

    def test_ca08_rechaza_total_declarado_distinto_de_la_suma_de_items(self):
        with self.assertRaisesMessage(ValidationError, "diferencia"):
            self.crear_compra(item_value="10000", total="12000")
        self.assertFalse(Compra.objects.filter(grupo=self.grupo).exists())

        self.client.force_login(self.admin)
        respuesta = self.client.post(
            reverse("nueva_compra", args=[self.grupo.pk]),
            {
                "fecha": "2026-11-10",
                "pagador": self.admin.pk,
                "descripcion": "Total incorrecto",
                "impuesto": "0",
                "descuento": "0",
                "total": "12000",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "20",
                "items-0-descripcion": "Producto",
                "items-0-valor": "10000",
                "items-0-beneficiarios": [str(self.admin.pk)],
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "diferencia")
        self.assertFalse(Compra.objects.filter(grupo=self.grupo).exists())

    def test_ca10_usuario_externo_no_puede_ver_el_grupo(self):
        externo = Usuario.objects.create_user(
            email="externo-flujos@test.com",
            password="ClaveSegura123!",
        )
        self.client.force_login(externo)
        respuesta = self.client.get(reverse("detalle_grupo", args=[self.grupo.pk]))
        self.assertEqual(respuesta.status_code, 403)

    def test_ca15_valida_total_con_iva_y_descuento(self):
        compra = self.crear_compra(
            item_value="20000",
            total="21800",
            impuesto="3800",
            descuento="2000",
        )
        self.assertEqual(compra.total, Decimal("21800"))
        self.assertEqual(compra.impuesto, Decimal("3800"))
        self.assertEqual(compra.descuento, Decimal("2000"))
        self.assertEqual(sum(calcular_saldos(self.grupo).values()), Decimal("0.00"))
        self.assertEqual(
            AjusteCompra.objects.filter(compra=compra).aggregate(total=Sum("monto"))["total"],
            Decimal("1800"),
        )

        with self.assertRaisesMessage(ValidationError, "diferencia"):
            self.crear_compra(
                item_value="20000",
                total="21801",
                impuesto="3800",
                descuento="2000",
            )
        self.client.force_login(self.admin)
        respuesta = self.client.post(
            reverse("nueva_compra", args=[self.grupo.pk]),
            {
                "fecha": "2026-11-10",
                "pagador": self.admin.pk,
                "descripcion": "Total IVA incorrecto",
                "impuesto": "3800",
                "descuento": "2000",
                "total": "21801",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "20",
                "items-0-descripcion": "Productos",
                "items-0-valor": "20000",
                "items-0-beneficiarios": [
                    str(self.admin.pk),
                    str(self.b.pk),
                    str(self.c.pk),
                ],
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "diferencia")
        self.assertEqual(Compra.objects.filter(grupo=self.grupo).count(), 1)

    def test_grupo_no_es_listado_a_usuarios_que_ya_fueron_retirados(self):
        retirar_integrante(self.admin, self.grupo.pk, self.c.pk)
        self.client.force_login(self.c)
        respuesta = self.client.get(reverse("inicio"))
        self.assertNotContains(respuesta, self.grupo.nombre)
        self.assertEqual(
            self.client.get(reverse("detalle_grupo", args=[self.grupo.pk])).status_code,
            403,
        )

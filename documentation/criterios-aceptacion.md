# Criterios de Aceptación (CA-01 a CA-15)

* **CA-01:** Crear un grupo e ingresar integrantes muestra correctamente los miembros registrados.
* **CA-02:** Registrar una compra válida (fecha, total, pagador) guarda el registro y permite consultarlo.
* **CA-03:** Dividir un gasto de $30.000 entre 3 integrantes en partes iguales asigna $10.000 a cada uno.
* **CA-04:** Registrar un abono o pago reduce el saldo pendiente y conserva el historial del pago.
* **CA-05:** Rechazar compras con valores negativos o campos obligatorios vacíos mostrando mensaje de error.
* **CA-06:** Completar el guardado y el recálculo de saldos en menos de 2 segundos bajo las condiciones de prueba.
* **CA-07:** Si A paga $30.000 repartidos entre A, B y C, A queda con $20.000 a favor y B y C con $10.000 de deuda cada uno.
* **CA-08:** Rechazar compras si la suma de ítems no coincide con el total, indicando la diferencia.
* **CA-09:** Modificar o anular compras, ítems o pagos recalcula los saldos y actualiza el resumen.
* **CA-10:** Permitir registro/login con contraseña hasheada y bloquear acceso a grupos no autorizados.
* **CA-11:** Impedir que un miembro edite o anule compras de otro integrante; permitirlo al administrador.
* **CA-12:** Pedir confirmación al anular una compra, marcarla como anulada junto con sus ítems/asignaciones, conservar pagos previos y registrar en auditoría.
* **CA-13:** Si A debe $10.000 a B y B debe $10.000 a C, sugerir una sola transferencia de A a C por $10.000.
* **CA-14:** Dividir $10.000 entre 3 integrantes asigna $3.334, $3.333 y $3.333, manteniendo la suma en $10.000 y el balance del grupo en cero.
* **CA-15:** Validar coherencia del total cuando hay ítems, IVA y descuentos (por ejemplo, ítems por $20.000 + IVA $3.800 - descuento $2.000 = $21.800).

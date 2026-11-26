# Reglas de Negocio y Modelo de Datos

## Entidades principales
* **Grupo e Integrante:** Identificadores, datos de acceso con contraseña cifrada mediante hash, membresía y rol dentro del grupo.
* **Compra, Ítem y Asignación:** Compra con fecha, total y pagador; ítems detallados y su distribución entre beneficiarios o categorías colectivas (**Hogar / Mascota**, tratadas como concepto colectivo y no como usuario con saldo propio).
* **Pago/Abono, Saldo e Historial:** Registro de abonos, cálculo dinámico de saldos y bitácora de ediciones o anulaciones.

## Reglas clave
* Toda compra debe tener fecha válida, monto mayor a cero y pagador perteneciente al grupo, y la suma de sus ítems debe coincidir con el total.
* El saldo de cada integrante refleja lo pagado menos lo asignado, manteniendo siempre un **balance cero** en la suma total del grupo.
* Las deudas cruzadas se simplifican para minimizar la cantidad de transferencias entre miembros.

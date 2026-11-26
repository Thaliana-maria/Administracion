# Reglas de Negocio y Modelo de Datos

## Entidades principales
* **Grupo e Integrante:** Identificadores, datos de acceso con contraseña cifrada mediante hash, membresía y rol dentro del grupo.
* **Compra, Ítem y Asignación:** Compra con fecha, total y pagador; ítems detallados y su distribución entre beneficiarios o categorías colectivas (**Hogar / Mascota**, tratadas como concepto colectivo y no como usuario con saldo propio).
* **Pago/Abono, Saldo e Historial:** Registro de abonos, cálculo dinámico de saldos y bitácora de ediciones o anulaciones.

## Reglas clave
* Toda compra debe tener fecha válida, monto mayor a cero y pagador perteneciente al grupo, y la suma de sus ítems debe coincidir con el total.
* El saldo de cada integrante refleja lo pagado menos lo asignado, manteniendo siempre un **balance cero** en la suma total del grupo.
* Las deudas cruzadas se simplifican para minimizar la cantidad de transferencias entre miembros.
* ## Entidades y campos principales

| Entidad | Campos y alcance en la ERS |
| :--- | :--- |
| **Grupo** | ID, nombre del grupo e integrantes vinculados |
| **Integrante** | ID, nombre, correo, contraseña con hash y estado dentro del grupo |
| **Compra** | ID, fecha, valor total, pagador asignado y grupo |
| **Ítem** | ID, descripción manual, valor monetario y compra asociada |
| **Asignación** | Relación entre ítem y beneficiarios (integrante individual, todos o categoría colectiva) |
| **Pago / Abono** | ID, acreedor, deudor, monto, fecha y estado de la deuda saldada |
| **Saldo** | Diferencia dinámica entre lo pagado y lo asignado/consumido |
| **Mascota / Hogar** | Categoría colectiva de reparto equitativo; no tiene saldo propio como usuario |
| **Historial de cambios** | ID, registro afectado, usuario, fecha y hora, acción (edición/anulación), valor anterior y nuevo |

{% hint style="info" %}
**Redondeo y cruce de deudas:** Al dividir un ítem entre varios beneficiarios se trunca a pesos enteros y el sobrante se reparte de a $1 empezando por el pagador (si es beneficiario) y siguiendo en orden alfabético (por ejemplo, $10.000 entre tres integrantes resulta en $3.334, $3.333 y $3.333). Si A debe $10.000 a B y B debe $10.000 a C, el sistema sugiere una sola transferencia de A a C por $10.000.
{% endhint %}

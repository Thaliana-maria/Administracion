# Requisitos Funcionales y No Funcionales

## Requisitos Funcionales (RF-01 a RF-13)
* **RF-01 (Grupos):** Crear grupos/casas e incorporar integrantes.
* **RF-02 y RF-03 (Compras e ítems):** Registrar compras manualmente (fecha, total, pagador) y desglosar cada ítem con su precio.
* **RF-04 (Asignación):** Asignar ítems a un integrante, repartir en partes iguales o identificar categorías como hogar o mascota.
* **RF-05, RF-06 y RF-09 (Saldos y resumen):** Calcular saldos a favor, deudas o saldo cero, mostrar resumen de cuentas pendientes y recalcular al crear, editar o anular registros.
* **RF-07 (Pagos y abonos):** Registrar pagos/abonos entre integrantes con pagador, receptor, monto, fecha e historial.
* **RF-08 (Validaciones):** Rechazar valores negativos, campos obligatorios vacíos o montos incoherentes.
* **RF-10 y RF-11 (Autenticación y roles):** Registro e inicio de sesión con hash de contraseñas, control de acceso por grupo y permisos de administrador vs. miembro.
* **RF-12 (Edición y anulación):** Modificar o anular compras, ítems o pagos cuidando la integridad contable y el historial.
* **RF-13 (Simplificación de deudas):** Calcular transferencias mínimas para saldar deudas cruzadas.

## Requisitos No Funcionales (RNF-01 a RNF-07)
* **RNF-01 y RNF-03:** Interfaz intuitiva basada en Figma y diseño adaptable (responsive) a escritorio, tableta y móvil.
* **RNF-02 y RNF-04:** Consistencia en cálculos y redondeos; respuesta menor a 2 segundos en grupos de hasta 20 integrantes y hasta 1.000 compras.
* **RNF-05, RNF-06 y RNF-07:** Hash unidireccional de contraseñas, estructura modular en Django y cumplimiento de la Ley 1581 de 2012 sobre protección de datos personales.

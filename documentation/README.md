# ¿Quién gastó esto? — Especificación y Documentación

Aplicación web desarrollada con **Python y Django** (interfaz en **HTML, CSS y JavaScript** siguiendo diseños de **Figma**) para registrar compras compartidas, desglosar productos, calcular saldos y simplificar deudas entre integrantes de un grupo, hogar o familia.

## Alcance de la versión actual
* **Registro 100 % manual:** Ingreso de compras, ítems, precios y abonos sin OCR ni lectura automática de facturas.
* **Grupos y roles:** Creación de grupos, gestión de integrantes, rol de miembro estándar y rol de administrador del grupo.
* **Asignación y categorías:** Asignación individual, compartida en partes iguales o mediante categorías colectivas como **Hogar** y **Mascota** (sin reparto proporcional por porcentajes en esta versión).
* **Saldos, compensaciones y auditoría:** Cálculo dinámico de saldos, invariante de balance cero, sugerencia de transferencias mínimas y registro de cambios.

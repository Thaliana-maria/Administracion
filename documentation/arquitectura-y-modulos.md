# Arquitectura y Módulos

El proyecto está organizado en aplicaciones de Django separadas por responsabilidad:

* **accounts:** Controla el registro, autorización de acceso, roles y permisos de los integrantes.
* **expenses:** Administra el registro de gastos/compras y las rutas de consulta y gestión de compensaciones.
* **ledger:** Maneja los saldos entre usuarios, registros de pago y confirmación/aplicación de compensaciones.
* **auditlog:** Registra los eventos clave (roles, compras, pagos y saldos) para auditoría.
* **config:** Centraliza ajustes del sistema, rutas principales y límites de acceso en producción.
* **templates / static:** Contiene las plantillas HTML (incluyendo vistas de dashboard, pagos y adaptación móvil) y archivos estáticos.

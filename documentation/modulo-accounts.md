# Cuentas, Roles y Permisos (accounts)

El módulo `accounts` administra el acceso y los permisos de los integrantes dentro del sistema:

* **Registro y autenticación:** Alta de usuarios con correo y contraseña (almacenada con hash seguro) e inicio de sesión.
* **Control de grupos:** Verificación de pertenencia al grupo para impedir el acceso a datos de grupos ajenos.
* **Roles:**
  * **Miembro / Participante:** Registra compras e ítems, asigna gastos y consulta saldos y deudas del grupo.
  * **Administrador del grupo:** Cuenta con los permisos de miembro más la gestión de integrantes y la edición/anulación de compras o pagos.

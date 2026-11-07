# Arquitectura sencilla del proyecto

El proyecto usa Django con el patrón MVT, equivalente en responsabilidades a MVC.

- Model: `accounts/models.py`, `expenses/models.py`, `ledger/models.py` y `auditlog/models.py`.
- Controller: `accounts/views.py` y las rutas de `config/urls.py`. Los servicios contienen los cálculos de negocio.
- View: las plantillas HTML ubicadas en `templates/`.

La separación en aplicaciones permite que cada integrante trabaje en su módulo y luego se integre en el mismo proyecto. No se crean proyectos separados ni se duplican modelos.

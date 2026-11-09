# Funcionalidades añadidas

- Dashboard por grupo, accesible desde «Mis grupos».
- Compras: formulario de ítems y vista previa del valor con JavaScript.
- RF-06: saldos y deudas calculados con reparto equitativo entre miembros activos. Se considera que quien registra una compra la pagó.
- RF-07: registro de transferencias entre integrantes e historial.
- Diseño responsive para estas pantallas.

## Instalación

Desde la carpeta `QGE`:

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Inicia sesión, crea un grupo y selecciona «Abrir dashboard». Para registrar pagos entre personas, el grupo debe tener al menos dos miembros activos.

**Alcance:** se asume reparto igualitario, sin asignación de cuotas individuales. Los pagos son registros manuales, no transferencias bancarias reales. No se modificaron los archivos de Figma.

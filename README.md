# ¿Quién Gastó Esto?

Aplicación web desarrollada con Django para administrar gastos compartidos entre integrantes de grupos, distribuir compras y calcular saldos.

## Tecnologías
- Python
- Django 5.2
- SQLite
- HTML y CSS
- Git y GitHub

## Arquitectura
El proyecto utiliza el patrón MVT (Modelo, Vista y Plantilla) de Django, equivalente en responsabilidades a MVC.

## Aplicaciones
- accounts: registro, usuarios e inicio de sesión.
- expenses: grupos, membresías, compras, artículos y asignaciones.
- ledger: pagos y cálculo de saldos.
- auditlog: auditoría.
- config: configuración y rutas generales.
- templates: plantillas HTML.

## Instalación

1. Crear entorno virtual:

   python -m venv .venv

2. Activarlo en Windows:

   .\.venv\Scripts\Activate.ps1

3. Instalar dependencias:

   pip install -r requirements.txt

4. Aplicar migraciones:

   python manage.py migrate

5. Ejecutar el servidor:

   python manage.py runserver

6. Abrir http://127.0.0.1:8000/

## Pruebas

Ejecutar todas las pruebas:

   python manage.py test

Resultado de la última ejecución: 17 pruebas aprobadas.

## Desarrollo por partes

La Parte 1 comprende la estructura inicial, autenticación, modelos iniciales, distribución de gastos mediante RN-05, cálculo de saldos y pruebas automatizadas.

Las demás funcionalidades serán desarrolladas por los integrantes del equipo e integradas en este mismo proyecto.

El equipo trabaja sobre un único proyecto y repositorio, sin duplicar modelos ni crear proyectos separados.

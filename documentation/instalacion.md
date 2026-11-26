# Instalación local

En Windows, desde la carpeta del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Abre http://127.0.0.1:8000/. Para ejecutar las pruebas: `python manage.py test -v 2`. Las 101 pruebas escritas están pendientes de ejecución verificada. Consulta la introducción para configuración y actualización de bases existentes.

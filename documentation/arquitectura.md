# Arquitectura y módulos

## Arquitectura del sistema: cliente-servidor

La aplicación utiliza una arquitectura cliente-servidor con tres capas lógicas: presentación, procesamiento y persistencia. Los usuarios acceden desde el navegador de un computador o celular. El servidor Django recibe las solicitudes HTTP, valida los permisos, ejecuta las reglas del negocio y consulta o modifica la base de datos mediante el ORM. Devuelve páginas HTML al navegador.

### Diagrama de arquitectura del sistema

```mermaid
flowchart LR
    subgraph CL["Cliente - capa de presentación"]
        PC["Computador / navegador"]
        MOV["Celular / navegador"]
        UI["Interfaz web: HTML, CSS y JavaScript"]
        PC --- UI
        MOV --- UI
    end
    subgraph SV["Servidor - capa de procesamiento"]
        WEB["Aplicación web Python / Django"]
        SEG["Autenticación, sesiones y permisos"]
        NEG["Gestión de grupos, compras, pagos y saldos"]
        ORM["ORM de Django"]
        WEB --> SEG
        SEG --> NEG
        NEG <--> ORM
    end
    subgraph DAT["Capa de persistencia"]
        BD[("SQLite: db.sqlite3")]
        PG[("PostgreSQL: opción configurable")]
    end
    UI -->|"Solicitudes HTTP / HTTPS"| WEB
    WEB -->|"Respuestas HTML y recursos web"| UI
    ORM <-->|"Lectura y escritura local"| BD
    ORM <-.->|"Conexión alternativa"| PG
```

| Componente | Responsabilidad |
| --- | --- |
| Cliente | Presentar la interfaz, capturar datos y enviar solicitudes. |
| Servidor | Autenticar usuarios, validar datos, ejecutar cálculos y generar respuestas. |
| Persistencia | Almacenar usuarios, grupos, compras, obligaciones, pagos e historial. |

El navegador no accede directamente a la base de datos. SQLite es la opción predeterminada y se ejecuta dentro del entorno del servidor, sin un servidor de base de datos independiente. PostgreSQL es una alternativa prevista en la configuración, no una segunda base utilizada simultáneamente. Las tres capas son lógicas y no implican tres máquinas físicas. HTTP se utiliza en desarrollo local y HTTPS es obligatorio con la configuración de producción. No se presupone un proveedor de alojamiento ni un despliegue de producción verificado.

## Arquitectura de software: monolito modular MVC/MVT

Trabajamos con una arquitectura MVC dentro de un monolito modular. Esto significa que tenemos un solo proyecto dividido en módulos que cumplen diferentes responsabilidades. Django utiliza el patrón MVT, que en nuestro proyecto se relaciona con MVC de la siguiente manera:

| MVC | En Django | Responsabilidad |
| --- | --- | --- |
| Modelo | models.py | Representa y guarda la información. |
| Vista | templates | Muestra la información al usuario. |
| Controlador | urls.py y views.py | Recibe las solicitudes y coordina las respuestas. |
| Apoyo a la lógica | services y forms | Realiza cálculos, aplica reglas y valida los datos. |

### Diagrama de arquitectura MVC

```mermaid
flowchart TD
    U[Usuario] --> N[Navegador]
    N --> R[Rutas de Django]
    R --> C[Controlador: views.py]
    C --> F[Formularios y validaciones]
    C --> S[Servicios y reglas del negocio]
    S --> M[Modelos]
    C --> M
    M <--> B[(Base de datos)]
    S --> C
    C --> V[Vista: plantillas HTML]
    V --> N
```

### Diagrama de componentes internos del software

```mermaid
flowchart LR
    subgraph Cliente
        A[Navegador]
        H[HTML CSS JavaScript]
    end
    subgraph Servidor Django
        R[config y rutas]
        AC[accounts]
        EX[expenses]
        LE[ledger]
        AU[auditlog]
        R --> AC
        R --> EX
        EX --> LE
        EX --> AU
        LE --> AU
    end
    A <--> R
    H --> A
    AC --> DB[(SQLite o PostgreSQL)]
    EX --> DB
    LE --> DB
    AU --> DB
```

Este diagrama representa los componentes del proyecto, no una infraestructura de alojamiento que hayamos verificado en producción.


## Arquitectura de base de datos

Las entidades principales son:

| Entidad | Información que guarda |
| --- | --- |
| Usuario | Correo, nombre y datos de autenticación. |
| Grupo | Nombre, creador, fecha de creación y estado de archivado. |
| Membresia | Usuario, grupo, rol y estado activo. |
| Compra | Grupo, pagador, fecha, total, impuesto y descuento. |
| Item | Artículo de una compra y su valor. |
| Asignacion | Parte del valor que corresponde a un beneficiario. |
| AjusteCompra | Valor de ajuste asignado a un beneficiario. |
| Obligacion | Deuda asociada a una asignación. |
| Pago | Transferencia entre deudor y acreedor, con estado pendiente, confirmado o rechazado. |
| RevisionCompra | Estado de revisión de una compra por cada usuario afectado. |
| OperacionRegistro | Clave única para evitar registros duplicados de compras y pagos. |
| AplicacionPago | Parte de un pago aplicada a una obligación. |
| Compensacion | Grupo, solicitante, deudor, acreedor, monto, estado, clave y fechas. |
| AprobacionCompensacion | Respuesta individual y fecha de cada participante. |
| TramoCompensacion | Obligación original, orden y monto reservado o aplicado. |
| Historial | Usuario, acción, registro afectado, detalles y fecha. |

### Diagrama entidad-relación

El siguiente diagrama muestra las relaciones principales de los modelos propios del proyecto. No incluye todas las tablas internas de autenticación de Django ni los campos de auditoría repetidos.

```mermaid
erDiagram
    USUARIO ||--o{ GRUPO : crea
    USUARIO ||--o{ MEMBRESIA : pertenece
    GRUPO ||--o{ MEMBRESIA : contiene
    GRUPO ||--o{ COMPRA : registra
    USUARIO ||--o{ COMPRA : paga
    USUARIO o|--o{ COMPRA : registra
    COMPRA ||--o{ ITEM : contiene
    ITEM ||--o{ ASIGNACION : distribuye
    USUARIO ||--o{ ASIGNACION : recibe
    COMPRA ||--o{ AJUSTE_COMPRA : tiene
    USUARIO ||--o{ AJUSTE_COMPRA : recibe
    ASIGNACION ||--o| OBLIGACION : genera
    GRUPO ||--o{ OBLIGACION : contiene
    USUARIO ||--o{ OBLIGACION : debe
    USUARIO ||--o{ OBLIGACION : cobra
    GRUPO ||--o{ PAGO : contiene
    USUARIO ||--o{ PAGO : envia
    USUARIO ||--o{ PAGO : recibe
    USUARIO o|--o{ PAGO : registra
    PAGO ||--o{ APLICACION_PAGO : distribuye
    OBLIGACION ||--o{ APLICACION_PAGO : recibe
    GRUPO ||--o{ COMPENSACION : contiene
    USUARIO ||--o{ COMPENSACION : solicita
    USUARIO ||--o{ COMPENSACION : envia
    USUARIO ||--o{ COMPENSACION : recibe
    COMPENSACION ||--o{ APROBACION_COMPENSACION : requiere
    USUARIO ||--o{ APROBACION_COMPENSACION : responde
    COMPENSACION ||--o{ TRAMO_COMPENSACION : contiene
    OBLIGACION ||--o{ TRAMO_COMPENSACION : vincula
    USUARIO ||--o{ HISTORIAL : realiza
    COMPRA ||--o{ REVISION_COMPRA : recibe
    USUARIO ||--o{ REVISION_COMPRA : revisa
    GRUPO ||--o{ OPERACION_REGISTRO : contiene
    USUARIO ||--o{ OPERACION_REGISTRO : solicita
    USUARIO {
        int id PK
        string email UK
        string first_name
        string last_name
    }
    GRUPO {
        int id PK
        int creador_id FK
        string nombre
        datetime fecha_creacion
        boolean archivado
    }
    MEMBRESIA {
        int id PK
        int grupo_id FK
        int usuario_id FK
        string rol
        boolean activo
    }
    COMPRA {
        int id PK
        int grupo_id FK
        int pagador_id FK
        int registrado_por_id FK
        date fecha
        decimal total
        decimal impuesto
        decimal descuento
        boolean anulada
    }
    ITEM {
        int id PK
        int compra_id FK
        string descripcion
        decimal valor
        boolean anulada
    }
    ASIGNACION {
        int id PK
        int item_id FK
        int beneficiario_id FK
        decimal valor_asignado
        boolean anulada
    }
    AJUSTE_COMPRA {
        int id PK
        int compra_id FK
        int beneficiario_id FK
        decimal monto
    }
    OBLIGACION {
        int id PK
        int asignacion_id FK
        int grupo_id FK
        int deudor_id FK
        int acreedor_id FK
        decimal monto
        boolean anulada
    }
    PAGO {
        int id PK
        int grupo_id FK
        int deudor_id FK
        int acreedor_id FK
        int registrado_por_id FK
        decimal monto
        date fecha
        string estado
        boolean anulada
    }
    REVISION_COMPRA {
        int id PK
        int compra_id FK
        int usuario_id FK
        string estado
    }
    OPERACION_REGISTRO {
        int id PK
        uuid clave UK
        string tipo
        int registro_id
        int grupo_id FK
        int usuario_id FK
    }
    APLICACION_PAGO {
        int id PK
        int pago_id FK
        int obligacion_id FK
        decimal monto
        boolean anulada
    }
    COMPENSACION {
        int id PK
        int grupo_id FK
        int solicitante_id FK
        int deudor_id FK
        int acreedor_id FK
        decimal monto
        string estado
        uuid clave UK
        datetime fecha
        datetime fecha_aplicacion
    }
    APROBACION_COMPENSACION {
        int id PK
        int compensacion_id FK
        int usuario_id FK
        string estado
        datetime fecha_respuesta
    }
    TRAMO_COMPENSACION {
        int id PK
        int compensacion_id FK
        int obligacion_id FK
        int orden
        decimal monto
    }
    HISTORIAL {
        int id PK
        int usuario_id FK
        string tipo_registro
        int id_registro
        string accion
        json detalles
        datetime fecha
    }
```

Historial identifica el registro afectado mediante su tipo e identificador, no mediante una llave foránea a cada tabla. OperacionRegistro también identifica la compra o el pago mediante tipo y registro_id. RevisionCompra tiene una restricción única por compra y usuario.

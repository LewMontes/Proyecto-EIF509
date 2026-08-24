# Arquitectura · Gastonomo

**Laboratorio 1 · EIF509 · II Ciclo 2026**

---

## 1 · Capas y su interacción

Este diagrama refleja **los archivos entregados** para el Laboratorio 1. Se sigue la regla de: **presentación → negocio → datos, nunca al revés**. Cada capa conoce únicamente a la
que tiene debajo.

```mermaid
flowchart TD
    Cliente["Cliente HTTP<br/><i>Swagger UI · curl · React (más adelante)</i>"]

    subgraph PRES["PRESENTACIÓN · src/app/presentation/"]
        direction TB
        RSalud["routers/salud.py<br/><i>GET /api/salud</i>"]
        RCat["routers/categorias.py<br/><i>POST y GET /api/categorias</i>"]
        Schemas["schemas.py<br/><i>DTOs de entrada y salida</i>"]
        Deps["dependencies.py<br/><i>arma el servicio con su repositorio</i>"]
        Errores["main.py · manejadores<br/><i>error de negocio → código HTTP</i>"]
    end

    subgraph NEG["NEGOCIO · src/app/business/"]
        direction TB
        SCat["services/categoria_service.py<br/><i>reglas, validaciones y transacción</i>"]
        Comando["CrearCategoriaComando<br/><i>orden que recibe el negocio</i>"]
        ErrNeg["errors.py<br/><i>violaciones del dominio</i>"]
    end

    subgraph DATOS["DATOS · src/app/data/"]
        direction TB
        RepoBase["repositories/base_repository.py<br/><i>CRUD genérico</i>"]
        RepoCat["repositories/categoria_repository.py<br/><i>consultas de categoría</i>"]
        Modelos["models/<br/>usuario.py · categoria.py · base.py · enums.py"]
    end

    subgraph CONF["CONFIGURACIÓN · src/app/config/"]
        direction TB
        Settings["settings.py<br/><i>nombre, versión, URL de la base</i>"]
        DB["database.py<br/><i>motor, sesión y creación de tablas</i>"]
    end

    BD[("SQLite hoy<br/>PostgreSQL después")]

    Cliente -->|JSON| RSalud
    Cliente -->|JSON| RCat
    RCat --> Schemas
    RCat --> Deps
    Deps --> SCat
    RCat --> Comando
    Comando --> SCat
    SCat --> ErrNeg
    ErrNeg -.->|se traduce en| Errores
    SCat --> RepoCat
    RepoCat --> RepoBase
    RepoCat --> Modelos
    RepoBase --> Modelos
    Modelos --> BD

    RSalud -.-> Settings
    Settings -.-> DB
    Deps -.-> DB
    DB --> BD

    classDef pres fill:#DBEAFE,stroke:#2563EB,color:#1E3A8A
    classDef neg fill:#DCFCE7,stroke:#16A34A,color:#14532D
    classDef dat fill:#FEF3C7,stroke:#D97706,color:#78350F
    classDef conf fill:#F3E8FF,stroke:#9333EA,color:#581C87
    classDef ext fill:#F1F5F9,stroke:#64748B,color:#0F172A

    class RSalud,RCat,Schemas,Deps,Errores pres
    class SCat,Comando,ErrNeg neg
    class RepoBase,RepoCat,Modelos dat
    class Settings,DB conf
    class Cliente,BD ext
```

### Qué hace cada capa

| Capa | Carpeta | Responsabilidad | Lo que tiene prohibido |
|---|---|---|---|
| **Presentación** | `presentation/` | Traducir JSON a comandos, llamar al servicio, traducir el resultado y convertir errores de negocio en códigos HTTP. | Calcular, validar reglas o consultar la base. |
| **Negocio** | `business/` | Reglas del dominio y validaciones. Es el dueño de la transacción: decide cuándo confirmar. | Saber que existe HTTP o escribir SQL. |
| **Datos** | `data/` | Entidades y consultas. Es el único lugar que sabe cómo se leen y guardan los datos. | Contener reglas de negocio o confirmar transacciones. |
| **Configuración** | `config/` | Valores que cambian entre máquinas y el motor de conexión. | Contener lógica del dominio. |

### Cómo se sostiene la regla en Python

Python no impide que un router importe un repositorio, así que la separación se mantiene con tres
decisiones explícitas del código:

1. **El servicio recibe una dataclass propia** (`CrearCategoriaComando`), no un modelo de Pydantic.
   Si recibiera modelos de FastAPI, el negocio quedaría amarrado a la forma de la API y no se
   podría reutilizar desde un script o una tarea programada.
2. **El repositorio nunca confirma.** Solo agrega y consulta; el `commit` lo hace el servicio, que
   es el único que sabe si la operación de negocio completa terminó bien. Ese límite es el que más
   adelante sostiene el proceso de conciliación, que escribe en cinco tablas.
3. **Los errores de negocio son excepciones propias** (`business/errors.py`), sin ninguna
   referencia a HTTP. `main.py` es el único archivo autorizado a mapearlos a códigos de respuesta.

---

## 2 · Recorrido de una petición

Ejemplo real y verificable hoy: crear una categoría colgada de otra.

```mermaid
sequenceDiagram
    autonumber
    participant C as Cliente
    participant R as routers/categorias.py<br/>(presentación)
    participant D as dependencies.py<br/>(presentación)
    participant S as CategoriaService<br/>(negocio)
    participant P as CategoriaRepository<br/>(datos)
    participant BD as Base de datos

    C->>R: POST /api/categorias
    R->>D: pide el servicio
    D->>D: abre la sesión de base de datos
    D-->>R: CategoriaService(CategoriaRepository(sesión))
    R->>R: convierte el JSON en CrearCategoriaComando
    R->>S: crear(comando)
    S->>S: valida nombre y color
    S->>P: buscar_por_nombre (¿ya existe?)
    P->>BD: SELECT
    S->>P: obtener_por_id (¿la padre es del mismo usuario?)
    P->>BD: SELECT
    S->>S: marca la padre como no-hoja
    S->>P: agregar(categoria)
    S->>BD: COMMIT
    S-->>R: Categoria
    R-->>C: 201 · CategoriaResponse

    Note over S,R: Si el nombre está repetido, el servicio lanza<br/>ReglaDeNegocioViolada y main.py la traduce a 409.
```

---

## 3 · Modelo de dominio

Las **once entidades** de la propuesta y sus relaciones. Este es el modelo objetivo del curso
completo, no el del código entregado: en el Laboratorio 1 solo están implementadas `USUARIO` y
`CATEGORIA` (marcadas en la tabla de abajo). La justificación de cada entidad está en
[`docs/propuesta-dominio.md`](propuesta-dominio.md).

```mermaid
erDiagram
    USUARIO ||--o{ CUENTA_CORREO : vincula
    USUARIO ||--o{ CATEGORIA : define
    USUARIO ||--o{ METODO_PAGO : registra
    USUARIO ||--o{ PRESUPUESTO : establece
    USUARIO ||--o{ REGLA_CATEGORIZACION : configura
    USUARIO ||--o{ COMPRA : realiza

    CUENTA_CORREO ||--o{ COMPROBANTE : entrega

    CATEGORIA ||--o{ CATEGORIA : "es padre de"
    CATEGORIA ||--o{ LINEA_COMPRA : clasifica
    CATEGORIA ||--o{ PRESUPUESTO : "se limita en"
    CATEGORIA ||--o{ REGLA_CATEGORIZACION : "es destino de"
    CATEGORIA ||--o{ COMERCIO : "es sugerida por"

    COMERCIO ||--o{ COMPRA : "es lugar de"
    METODO_PAGO ||--o{ COMPRA : paga

    COMPRA ||--|{ LINEA_COMPRA : "se desglosa en"
    COMPRA |o--o| COMPROBANTE : "se concilia con"

    USUARIO {
        int id PK
        string nombre_completo
        string correo UK
        string contrasena_hash
        enum moneda_preferida
        bool activo
    }
    CUENTA_CORREO {
        int id PK
        int usuario_id FK
        string proveedor
        string direccion
        string token_acceso
        string token_refresco
        datetime expira_en
        datetime ultima_sincronizacion
        enum estado
    }
    CATEGORIA {
        int id PK
        int usuario_id FK
        int categoria_padre_id FK
        string nombre
        string color_hex
        bool es_hoja
        bool activa
    }
    COMERCIO {
        int id PK
        int categoria_sugerida_id FK
        string nombre
        string nombre_normalizado UK
        string identificacion_tributaria
        string provincia
    }
    METODO_PAGO {
        int id PK
        int usuario_id FK
        string alias
        enum tipo
        enum moneda
        string ultimos_cuatro
        int dia_corte
    }
    COMPRA {
        int id PK
        int usuario_id FK
        int comercio_id FK
        int metodo_pago_id FK
        date fecha
        enum moneda
        enum estado
        enum origen
        decimal subtotal
        decimal descuento
        decimal impuesto
        bool impuesto_desglosado
        decimal total
        decimal tipo_cambio_aplicado
        decimal total_moneda_base
    }
    LINEA_COMPRA {
        int id PK
        int compra_id FK
        int categoria_id FK
        string descripcion
        decimal cantidad
        decimal precio_unitario
        decimal descuento
        bool exento_impuesto
        decimal subtotal
        bool categorizada_automaticamente
    }
    PRESUPUESTO {
        int id PK
        int usuario_id FK
        int categoria_id FK
        int anio
        int mes
        decimal monto_limite
        decimal monto_consumido
        int umbral_alerta
        enum estado
    }
    REGLA_CATEGORIZACION {
        int id PK
        int usuario_id FK
        int categoria_destino_id FK
        string nombre
        enum campo
        string patron
        int prioridad
        bool activa
        int veces_aplicada
    }
    COMPROBANTE {
        int id PK
        int usuario_id FK
        int cuenta_correo_id FK
        int compra_id FK
        string mensaje_id UK
        string remitente
        datetime recibido_en
        enum estado
        int intentos_procesamiento
        string motivo_fallo
    }
    TIPO_CAMBIO {
        int id PK
        enum moneda_origen
        enum moneda_destino
        date fecha
        decimal tasa
        string fuente
    }
```

| Entidad | Laboratorio |
|---|---|
| `USUARIO`, `CATEGORIA` | **Implementadas en el Laboratorio 1** |
| Las nueve restantes | Pendientes para los laboratorios siguientes |

Dos notas de modelado que valen la pena:

> **`TIPO_CAMBIO` aparece suelto a propósito.** No tiene llave foránea hacia `COMPRA`: la compra
> guarda copiada la tasa que se le aplicó (`tipo_cambio_aplicado`), no una referencia. Si apuntara
> a la fila, corregir una tasa mal cargada cambiaría retroactivamente los totales de compras ya
> cerradas. Copiar el valor congela el histórico.

> **`COMERCIO` apunta a `CATEGORIA`, no al revés.** Es la categoría *sugerida* del comercio, la
> pieza que hace posible la clasificación automática: como el comprobante que llega por correo
> solo trae el nombre del negocio, el comercio es la única señal disponible para adivinar la
> categoría.

---

## 4 · Despliegue previsto

```mermaid
flowchart LR
    subgraph Nav["Navegador"]
        React["React SPA<br/><i>pendiente</i>"]
    end

    subgraph Servidor["Servidor de aplicación"]
        Uvicorn["Uvicorn + FastAPI<br/><i>entregado ✓</i>"]
    end

    subgraph Datos["Almacenamiento"]
        SQLite[("SQLite local<br/><i>entregado ✓</i>")]
        PG[("PostgreSQL<br/><i>pendiente</i>")]
    end

    subgraph Ext["Externos"]
        Correo["Buzones vinculados<br/><i>pendiente</i>"]
        BCCR["Tipos de cambio BCCR<br/><i>pendiente</i>"]
    end

    React -->|REST · JSON| Uvicorn
    React -->|WebSocket · gasto en vivo| Uvicorn
    Uvicorn --> SQLite
    Uvicorn -.->|reemplaza a SQLite| PG
    Correo -->|lee, extrae y descarta| Uvicorn
    BCCR -->|carga diaria de tasas| Uvicorn

    classDef hecho fill:#DCFCE7,stroke:#16A34A,color:#14532D
    classDef futuro fill:#F1F5F9,stroke:#94A3B8,color:#334155
    class Uvicorn,SQLite hecho
    class React,PG,Correo,BCCR futuro
```

> **Una sola base de datos.** El sistema no almacena los comprobantes: lee cada correo, le extrae
> los cuatro campos que necesita y descarta el contenido. Todo lo que se persiste tiene esquema
> fijo, así que PostgreSQL lo cubre entero y no hace falta una base documental.

En el Laboratorio 1 solo están construidas las cajas verdes: la aplicación FastAPI levantando,
respondiendo y guardando contra SQLite, con el esqueleto por capas listo para que las demás piezas
se conecten encima.

# Arquitectura · Gastonomo

**EIF509 · II Ciclo 2026 · actualizado en el Laboratorio 4**

> Este documento se actualiza en cada entrega. Las secciones § 1 y § 2 reflejan el código de hoy;
> la § 3 conserva el modelo de dominio del Laboratorio 1 con las notas de lo que cambió después, y
> la § 4 el despliegue.

---

## 1 · Capas y su interacción

Se sigue la regla de **presentación → negocio → datos, nunca al revés**. Cada capa conoce
únicamente a la que tiene debajo.

```mermaid
flowchart TD
    Cliente["Cliente HTTP<br/><i>React SPA · Swagger UI · curl</i>"]

    subgraph PRES["PRESENTACIÓN · src/app/presentation/"]
        direction TB
        Routers["routers/<br/><i>salud · categorias · comercios · metodos_pago ·<br/>presupuestos · reglas_categorizacion · compras</i>"]
        Schemas["schemas.py<br/><i>DTOs: validación de forma con Field(...)</i>"]
        Deps["dependencies.py<br/><i>arma cada servicio con sus repositorios</i>"]
        Errores["main.py · manejadores<br/><i>error de negocio → código HTTP</i>"]
    end

    subgraph NEG["NEGOCIO · src/app/business/"]
        direction TB
        Concil["conciliacion_service.py<br/><i>Proceso 2 · transacción de 5 tablas</i>"]
        Registro["registrar_compra_service.py<br/><i>Proceso 1 · captura manual</i>"]
        Reglas["categoria · comercio · metodo_pago ·<br/>presupuesto · regla_categorizacion<br/><i>reglas, cálculos y validaciones</i>"]
        Lectura["compra_service.py<br/><i>solo lectura</i>"]
        Externos["tipo_cambio_service.py<br/><i>habla con el BCCR, con respaldo en Hacienda</i>"]
        Comandos["CrearCategoriaComando · CrearMetodoPagoComando ·<br/>CrearReglaComando<br/><i>órdenes que recibe el negocio</i>"]
        Parsers["parsers/<br/><i>comprobante_bac</i>"]
        ErrNeg["errors.py<br/><i>violaciones del dominio, sin HTTP</i>"]
        Bitacora["bitacora_service.py<br/><i>trazabilidad, fuera de la transacción</i>"]
    end

    subgraph DATOS["DATOS · src/app/data/"]
        direction TB
        RepoBase["repositories/base_repository.py<br/><i>CRUD genérico tipado</i>"]
        Repos["14 repositorios específicos<br/><i>el único lugar que consulta datos</i>"]
        RepoMongo["bitacora_repository.py<br/><i>no hereda: Mongo no tiene sesión</i>"]
        Modelos["models/<br/><i>14 entidades mapeadas</i>"]
    end

    subgraph CONF["CONFIGURACIÓN · src/app/config/"]
        direction TB
        Settings["settings.py"]
        DB["database.py<br/><i>motor y sesión</i>"]
        HTTP["cliente_http.py"]
        Mongo["cliente_mongo.py"]
    end

    PG[("PostgreSQL<br/><i>SQLite en desarrollo</i>")]
    MG[("MongoDB<br/><i>bitacora_compras</i>")]

    Cliente -->|JSON| Routers
    Routers --> Schemas
    Routers --> Deps
    Routers --> Comandos
    Deps --> Concil
    Deps --> Reglas
    Deps --> Lectura
    Comandos --> Reglas
    Deps --> Registro
    Registro --> Reglas
    Registro --> Repos
    Concil --> Reglas
    Concil --> Parsers
    Concil --> Externos
    Concil --> Bitacora
    Reglas --> ErrNeg
    Externos --> ErrNeg
    ErrNeg -.->|único punto de traducción| Errores
    Concil --> Repos
    Reglas --> Repos
    Lectura --> Repos
    Bitacora --> RepoMongo
    Repos --> RepoBase
    Repos --> Modelos
    RepoBase --> Modelos
    Modelos --> PG
    RepoMongo --> MG

    Deps -.-> DB
    Deps -.-> HTTP
    Deps -.-> Mongo
    Settings -.-> DB
    DB --> PG
    Mongo --> MG

    classDef pres fill:#DBEAFE,stroke:#2563EB,color:#1E3A8A
    classDef neg fill:#DCFCE7,stroke:#16A34A,color:#14532D
    classDef dat fill:#FEF3C7,stroke:#D97706,color:#78350F
    classDef conf fill:#F3E8FF,stroke:#9333EA,color:#581C87
    classDef ext fill:#F1F5F9,stroke:#64748B,color:#0F172A

    class Routers,Schemas,Deps,Errores pres
    class Concil,Registro,Reglas,Lectura,Externos,Comandos,Parsers,ErrNeg,Bitacora neg
    class RepoBase,Repos,RepoMongo,Modelos dat
    class Settings,DB,HTTP,Mongo conf
    class Cliente,PG,MG ext
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
   es el único que sabe si la operación de negocio completa terminó bien. Ese límite es el que
   sostiene el proceso de conciliación, que escribe en cinco tablas -ver § 2.2.
3. **Los errores de negocio son excepciones propias** (`business/errors.py`), sin ninguna
   referencia a HTTP. `main.py` es el único archivo autorizado a mapearlos a códigos de respuesta.

Las reglas de cada proceso, los patrones de diseño aplicados y lo que queda abierto están en el
documento de la [Capa de negocio](negocio.md).

---

## 2 · Recorrido de una petición

### 2.1 · Un caso simple: crear una categoría colgada de otra

```mermaid
sequenceDiagram
    autonumber
    participant C as Cliente
    participant R as routers/categorias.py<br/>(presentación)
    participant D as dependencies.py<br/>(presentación)
    participant S as CategoriaService<br/>(negocio)
    participant P as CategoriaRepository<br/>(datos)
    participant U as UsuarioRepository<br/>(datos)
    participant BD as Base de datos

    C->>R: POST /api/categorias
    R->>D: pide el servicio
    D->>D: abre la sesión de base de datos
    D-->>R: CategoriaService(CategoriaRepository, UsuarioRepository)
    R->>R: convierte el JSON en CrearCategoriaComando
    R->>S: crear(comando)
    S->>S: valida nombre y color
    S->>U: obtener_por_id (¿el titular existe y está activo?)
    U->>BD: SELECT
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

### 2.2 · El caso transaccional: conciliar un comprobante

El Proceso 2 del dominio. Escribe en **cinco tablas** y todas tienen que ocurrir o ninguna: el
único `commit` está al final, y ningún repositorio confirma por su cuenta. Las reglas completas
están en [Capa de negocio § 2.1](negocio.md#21--proceso-2--ingesta-y-conciliación-de-un-comprobante-transaccional).

```mermaid
sequenceDiagram
    autonumber
    participant CC as CuentaCorreoService<br/>(negocio)
    participant S as ConciliacionService<br/>(negocio)
    participant MP as MetodoPagoRepository
    participant CO as ComercioService
    participant RG as ReglaCategorizacionRepository
    participant PR as PresupuestoRepository
    participant BD as PostgreSQL
    participant MG as MongoDB

    CC->>S: conciliar(usuario, comprobante, parseado)
    S->>S: ¿es compra, confiable y completa?
    Note over S: Si no, devuelve None: queda para<br/>revisión manual. No se inventa nada.

    S->>MP: buscar_por_ultimos_cuatro
    MP->>BD: SELECT
    Note over S,MP: Sin coincidencia no se crea ninguno:<br/>la compra queda requiere_revision.

    S->>CO: resolver_o_crear(comercio)
    CO->>BD: SELECT / INSERT + COMMIT propio
    Note over CO: Catálogo compartido: confirma aparte.<br/>Es un paso previo, no parte de la transacción.

    S->>RG: listar_activas_ordenadas
    RG->>BD: SELECT
    S->>S: cadena de categorización:<br/>regla → sugerencia del comercio → ninguna

    S->>BD: INSERT compra (flush, sin confirmar)
    S->>BD: INSERT linea_compra
    S->>BD: UPDATE regla.veces_aplicada
    S->>PR: buscar(categoría, año, mes)
    S->>BD: UPDATE presupuesto.monto_consumido
    S->>BD: UPDATE comprobante.compra_id

    S->>BD: COMMIT
    Note over S,BD: Las cinco escrituras, o ninguna.<br/>Cualquier excepción antes de acá revierte todo.

    S->>MG: registrar_evento × N
    Note over S,MG: Después del commit y nunca bloqueante:<br/>la bitácora explica, no decide.

    S-->>CC: ResultadoConciliacion
```

---

## 3 · Modelo de dominio

Las **once entidades** de la propuesta y sus relaciones, tal como se dibujaron en el Laboratorio 1.
Se conserva el diagrama original y la tabla de abajo dice en qué entrega se implementó cada parte;
el modelo real de hoy tiene 14 entidades y está en el
[Modelo de datos § 2.1](modelo-de-datos.md). La justificación de cada entidad está en la
[Propuesta de dominio](propuesta-dominio.md).

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
| `USUARIO`, `CATEGORIA` | Implementadas como clases en el Laboratorio 1 |
| Las once tablas del esquema, más `CATEGORIA_ESTANDAR` | **Creadas en PostgreSQL en el Laboratorio 2** |
| Las 14 entidades, con sus relaciones y su carga diferida razonada | **Mapeadas con SQLAlchemy en el Laboratorio 3** |
| `COMPRA`, `LINEA_COMPRA`, `PRESUPUESTO`, `REGLA_CATEGORIZACION`, `COMPROBANTE` | **Escritas dentro de una sola transacción en el Laboratorio 4** |

> **Actualizado en el Laboratorio 2.** El diagrama de arriba es el del Laboratorio 1. El modelo
> implementado de verdad agrega una entidad —`CATEGORIA_ESTANDAR`, la taxonomía global que siembra
> cada cuenta y a la que apuntan los comercios compartidos— y está en el
> [Modelo de datos § 2.1](modelo-de-datos.md), con la explicación del ajuste en la § 5.1.

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

## 4 · Despliegue

```mermaid
flowchart LR
    subgraph Nav["Cliente"]
        React["Cliente HTTP<br/><i>Swagger UI · curl</i>"]
    end

    subgraph Servidor["Servidor de aplicación"]
        Uvicorn["Uvicorn + FastAPI<br/><i>entregado ✓</i>"]
    end

    subgraph Datos["Almacenamiento"]
        SQLite[("SQLite local<br/><i>solo desarrollo</i>")]
        PG[("PostgreSQL<br/><i>conectado ✓</i>")]
        Mongo[("MongoDB<br/><i>bitacora_compras ✓</i>")]
    end

    subgraph Ext["Externos"]
        Correo["Buzones vinculados<br/><i>Outlook · Gmail ✓</i>"]
        BCCR["Tipos de cambio<br/><i>BCCR · Hacienda ✓</i>"]
    end

    React -->|REST · JSON| Uvicorn
    Uvicorn -->|desarrollo| SQLite
    Uvicorn -->|producción| PG
    Uvicorn -->|trazabilidad de la compra| Mongo
    Correo -->|lee, extrae y descarta| Uvicorn
    BCCR -->|tasa de la fecha| Uvicorn

    classDef hecho fill:#DCFCE7,stroke:#16A34A,color:#14532D
    classDef futuro fill:#F1F5F9,stroke:#94A3B8,color:#334155
    class Uvicorn,PG,Mongo,React,Correo,BCCR hecho
    class SQLite futuro
```

> **Una sola base de datos.** El sistema no almacena los comprobantes: lee cada correo, le extrae
> los cuatro campos que necesita y descarta el contenido. Todo lo que se persiste tiene esquema
> fijo, así que PostgreSQL lo cubre entero y no hace falta una base documental.
>
> **Revisado en el Laboratorio 2.** El sistema pasó a **persistencia políglota**: el núcleo sigue
> completo en PostgreSQL —esa parte no cambió— y se sumó MongoDB con una sola colección,
> `bitacora_compras`, que guarda la trazabilidad de cada compra. Los comprobantes siguen sin
> almacenarse. Ver [ADR-002](adr/ADR-002-subdominio-documental-en-mongodb.md) y el
> [Modelo de datos](modelo-de-datos.md).

`docker compose up -d` levanta PostgreSQL, el contenedor de Flyway que aplica las migraciones y
los datos de ejemplo, y MongoDB con su colección ya validada. La aplicación corre aparte y se
conecta a las dos: `GASTONOMO_URL_BASE_DATOS` apunta el ORM a PostgreSQL en lugar de SQLite, y
`BitacoraComprasService` escribe la trazabilidad en MongoDB desde la conciliación real.

> **Una salvedad de esquema.** La aplicación en ejecución crea sus tablas con
> `Base.metadata.create_all()`, no con Flyway. Las migraciones de
> [`db/postgres/migrations/`](../db/postgres/migrations/) son la fuente de verdad documentada del
> modelo, pero todavía no son la que la aplicación aplica al arrancar. Está declarado como
> pendiente en [Capa de negocio § 8](negocio.md#8--lo-que-queda-abierto).

# Gastonomo · Control de gastos personales por categorías

Sistema web multiusuario donde cualquier persona crea su cuenta, vincula el buzón donde le llegan
sus comprobantes de compra, y el sistema clasifica su gasto por categoría mostrándole en vivo el
avance contra su presupuesto mensual.

**EIF509 Desarrollo de Aplicaciones Basadas en Web · II Ciclo 2026**
Universidad Nacional · Escuela de Informática

| |                                                         |
|---|---------------------------------------------------------|
| **Integrantes** | Jose Alexis Solís Carvajal · 1-1623-0238          |
|  |    Luis Antonio Montes de Oca Ruiz · 1-1800-0270     |
| **Entrega actual** | Laboratorio 1 — Arquitectura base y esqueleto por capas |

---

## Stack

**Python 3.14 · FastAPI · SQLAlchemy 2.0 · PostgreSQL · React**

> El curso recomienda Java 21 + Spring Boot 3. Este equipo solicitó y obtuvo autorización del
> profesor para usar un stack alternativo equivalente. La justificación técnica completa —con las
> alternativas descartadas y lo que la decisión nos cuesta— está en
> [ADR-001](docs/adr/ADR-001-eleccion-del-stack.md).

---

## Qué incluye este laboratorio

El Laboratorio 1 entrega **la arquitectura, no el sistema**. Es el esqueleto por capas funcionando
de punta a punta con dos entidades del dominio —`Categoria`, que es el eje del sistema, y
`Usuario`, que es su dueña— para demostrar la estructura sin adelantar trabajo de los laboratorios
siguientes.

El dominio completo —once entidades y dos procesos de negocio— está diseñado y documentado en la
[Propuesta de Dominio](docs/propuesta-dominio.md); se implementa en los laboratorios siguientes.

---

## Cómo correrlo

Necesita **Python 3.12 o superior** (se usó 3.14). **No hace falta instalar ninguna base
de datos**: en este laboratorio la aplicación usa SQLite local y crea el archivo sola al arrancar.

### 1. Clonar y crear el entorno virtual

```bash
git clone https://github.com/LewMontes/Proyecto-EIF509-Personal.git
```

```bash
python -m venv .venv
```

Activarlo — en **Windows (PowerShell)**:

```bash
.venv\Scripts\Activate.ps1
```

En **Mac / Linux**:

```bash
source .venv/bin/activate
```

### 2. Instalar las dependencias

```bash
pip install -e ".[dev]"
```

### 3. Levantar la aplicación

```bash
uvicorn app.main:app --reload --app-dir src
```

### 4. Probarla

Con la app corriendo, en otra terminal:

```bash
curl http://localhost:8000/api/salud
```

Respuesta esperada:

```json
{"estado":"OK - sistema en linea","aplicacion":"Gastonomo","version":"0.1.0"}
```

La documentación interactiva de la API se genera sola. Se puede abrir en el navegador:

- **Swagger UI** → http://localhost:8000/docs
- **ReDoc** → http://localhost:8000/redoc

### Endpoints disponibles

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/api/salud` | Confirma que el sistema está en línea |
| `POST` | `/api/categorias` | Crea una categoría aplicando las reglas del dominio |
| `GET` | `/api/categorias?usuario_id=1` | Lista las categorías activas de un usuario |

### 5. Correr las pruebas y el linter

```bash
pytest -v
```

```bash
ruff check . && ruff format --check .
```

Son los mismos comandos que ejecuta la integración continua. Las pruebas corren contra una base
SQLite **en memoria**, así que no tocan ningún archivo ni necesitan infraestructura.

---

## Cómo está organizado

Arquitectura en tres capas más configuración. La regla de oro:
**presentación → negocio → datos, nunca al revés.**

```
src/app/
├── presentation/   → Habla HTTP. Recibe JSON, llama al servicio, devuelve JSON.
│   ├── routers/        salud.py · categorias.py
│   ├── schemas.py      DTOs de entrada y salida
│   └── dependencies.py arma el servicio con su repositorio
│
├── business/       → Reglas del negocio. No sabe que existe HTTP.
│   ├── services/       categoria_service.py
│   └── errors.py       violaciones de reglas del dominio
│
├── data/           → Entidades y consultas. No contiene reglas de negocio.
│   ├── models/         usuario.py · categoria.py · base.py · enums.py
│   └── repositories/   el único lugar del sistema que consulta datos
│
├── config/         → Lo que cambia entre máquinas.
│   ├── settings.py     nombre, versión, URL de la base
│   └── database.py     motor, sesión y creación de tablas
│
└── main.py         → Arma la app y traduce errores de negocio a códigos HTTP.
```

Tres decisiones sostienen la separación, ya que Python no la impone por sí solo:

1. El servicio recibe una **dataclass propia** (`CrearCategoriaComando`), no un modelo de FastAPI.
2. El repositorio **nunca confirma la transacción**: el `commit` lo hace el servicio, que es el
   único que sabe si la operación de negocio completa terminó bien.
3. Los errores de negocio son **excepciones propias** sin ninguna referencia a HTTP; `main.py` es
   el único archivo que las traduce a códigos de respuesta.

---

## Documentación

| Documento | Qué contiene |
|---|---|
| [Propuesta de Dominio](docs/propuesta-dominio.md) | El negocio, los actores, las 11 entidades y los 2 procesos con sus reglas, cálculos y validaciones. |
| [Arquitectura](docs/arquitectura.md) | Diagramas de capas, recorrido de una petición, modelo entidad-relación y despliegue previsto. |
| [ADR-001 · Elección del stack](docs/adr/ADR-001-eleccion-del-stack.md) | Por qué Python + FastAPI + PostgreSQL + React, qué descartamos y qué nos cuesta. |

---

## Integración continua

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) corre en cada push y en cada pull request
sobre `main` y `master`. Instala el proyecto en una máquina limpia, revisa el código con `ruff`,
ejecuta la suite de pruebas y **levanta el servidor de verdad** para confirmar que `/api/salud`
responde.

El estado se ve en la pestaña **Actions** del repositorio y en la insignia del inicio de este
README.

---

## Estado del proyecto

El curso son siete laboratorios incrementales sobre esta misma base.

- [x] **Laboratorio 1** *(entregado)* — Arquitectura por capas, `Usuario` y `Categoria`, propuesta de dominio, CI

Pendiente para los laboratorios siguientes:

- [ ] PostgreSQL con migraciones y las nueve entidades restantes del dominio
- [ ] Frontend React con avance de presupuesto en vivo
- [ ] Proceso transaccional de ingesta y conciliación de comprobantes
- [ ] Autenticación, roles y vinculación del buzón de correo

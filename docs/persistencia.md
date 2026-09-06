# Capa de persistencia · Gastonomo

**Laboratorio 3 · EIF509 Desarrollo de Aplicaciones Basadas en Web · II Ciclo 2026 · Grupo G01**

Jose Alexis Solís Carvajal · 1-1623-0238
Luis Antonio Montes de Oca Ruiz · 1-1800-0270

---

El [Laboratorio 2](modelo-de-datos.md) entregó el esquema: tablas, restricciones e índices. Este
documento entrega **cómo la aplicación habla con ese esquema**: el mapeo objeto-relacional, los
repositorios, las consultas de negocio que expone, el problema N+1 que producía la lista de compras
y cómo se corrigió, y cómo se prueba todo contra una base real.

> **Nota sobre el ORM.** El curso plantea el laboratorio sobre JPA/Hibernate. Este equipo trabaja
> con **SQLAlchemy 2.0** bajo la autorización de stack alternativo que documenta
> [ADR-001](adr/ADR-001-eleccion-del-stack.md). La correspondencia es directa:

| JPA / Hibernate | SQLAlchemy 2.0 |
|---|---|
| `@Entity` sobre una clase | Clase que hereda de `DeclarativeBase` |
| `@ManyToOne` / `@OneToMany` | `relationship()` con `back_populates` |
| `FetchType.LAZY` | `lazy="select"` (el default, escrito explícito) |
| JPQL | `select()` del ORM, tipado sobre las entidades |
| Criteria API / Specifications | El mismo `select()`, construido por partes |
| `JOIN FETCH` / `@EntityGraph` | `joinedload()` / `selectinload()` |
| `ddl-auto=validate` | Comparación del mapeo contra el `Inspector` ([§6](#6--cómo-se-prueba)) |

---

## 1 · Qué compone la capa

| Pieza | Dónde vive | Qué hace |
|---|---|---|
| Base declarativa | [`data/models/base.py`](../src/app/data/models/base.py) | Raíz del mapeo. `Base.metadata` conoce el esquema completo. |
| Entidades | [`data/models/`](../src/app/data/models/) | 14 clases mapeadas, más los `StrEnum` del dominio y un `TypeDecorator` de fecha-hora UTC. |
| Repositorio genérico | [`data/repositories/base_repository.py`](../src/app/data/repositories/base_repository.py) | CRUD común, parametrizado por entidad. |
| Repositorios por entidad | [`data/repositories/`](../src/app/data/repositories/) | 14 repositorios relacionales con las consultas propias de cada agregado. |
| Repositorio documental | [`data/repositories/bitacora_repository.py`](../src/app/data/repositories/bitacora_repository.py) | La colección `bitacora_compras` de MongoDB. |
| Motor y sesión | [`config/database.py`](../src/app/config/database.py) | Un motor por proceso, una sesión por petición. |

La regla que sostiene la separación, la misma desde el Laboratorio 1: **el repositorio consulta y
agrega, pero nunca confirma la transacción**. El `commit` lo hace el servicio, que es el único que
sabe si la operación de negocio completa terminó bien. Es esa frontera la que permite que
`ConciliacionService` escriba en cinco tablas dentro de una sola transacción.

---

## 2 · El mapeo objeto-relacional

### 2.1 · Las entidades y sus relaciones

Catorce entidades, veinte llaves foráneas, **cuarenta declaraciones de `relationship()`**: los
veinte pares bidireccionales que corresponden a esas veinte llaves.

| Entidad | Tabla | Llaves foráneas | Relaciones navegables |
|---|---|---|---|
| `Usuario` | `usuario` | — | `categorias`, `cuentas_correo`, `metodos_pago`, `compras`, `presupuestos`, `reglas_categorizacion`, `categorias_sugeridas` |
| `Categoria` | `categoria` | `usuario_id`, `categoria_padre_id`, `categoria_estandar_id` | `usuario`, `categoria_padre`, `subcategorias`, `categoria_estandar`, `lineas`, `presupuestos`, `reglas_destino`, `sugerencias` |
| `CategoriaEstandar` | `categoria_estandar` | — | `categorias` |
| `CuentaCorreo` | `cuenta_correo` | `usuario_id` | `usuario`, `comprobantes`, `transferencias_sinpe` |
| `Comercio` | `comercio` | — | `compras`, `categorias_sugeridas` |
| `ComercioCategoriaSugerida` | `comercio_categoria_sugerida` | `usuario_id`, `comercio_id`, `categoria_id` | `usuario`, `comercio`, `categoria` |
| `MetodoPago` | `metodo_pago` | `usuario_id` | `usuario`, `compras` |
| `Compra` | `compra` | `usuario_id`, `comercio_id`, `metodo_pago_id` | `usuario`, `comercio`, `metodo_pago`, `lineas`, `comprobantes` |
| `LineaCompra` | `linea_compra` | `compra_id` *(ON DELETE CASCADE)*, `categoria_id` | `compra`, `categoria` |
| `Comprobante` | `comprobante` | `cuenta_correo_id`, `compra_id` | `cuenta_correo`, `compra` |
| `TransferenciaSinpe` | `transferencia_sinpe` | `cuenta_correo_id` | `cuenta_correo` |
| `Presupuesto` | `presupuesto` | `usuario_id`, `categoria_id` | `usuario`, `categoria` |
| `ReglaCategorizacion` | `regla_categorizacion` | `usuario_id`, `categoria_destino_id` | `usuario`, `categoria_destino` |
| `TipoCambio` | `tipo_cambio` | — | — *(catálogo de tasas: no referencia a nadie ni nadie a él)* |

Las catorce se importan desde
[`data/models/__init__.py`](../src/app/data/models/__init__.py) a propósito. SQLAlchemy resuelve
las relaciones **por nombre de clase**, y solo conoce las clases que ya se importaron: sin esa
lista, qué relaciones resuelven dependería del orden accidental en que cada punto de entrada fuera
importando modelos.

### 2.2 · El criterio de carga: perezosa siempre

Las cuarenta relaciones declaran `lazy="select"` explícitamente. Es el default de SQLAlchemy y el
equivalente del `FetchType.LAZY` de JPA: la relación no se toca hasta que alguien la lee. Está
escrito y no omitido para que se lea como una decisión.

El criterio, en una frase: **nunca cargar de más por el solo hecho de navegar al padre.** Donde más
se nota es en `Usuario`, la raíz de aislamiento del sistema: se carga en cada petición autenticada
solo para validar el token. Con carga ansiosa, ese `SELECT` arrastraría el historial completo del
titular -sus compras, sus comprobantes, sus presupuestos- en cada llamada a cualquier endpoint.

**La carga ansiosa se decide por consulta, no en el mapeo.** Donde se sabe que el dato se va a
usar, la consulta lo pide (`CompraRepository._relaciones_del_detalle`); donde no, no se paga.
Ese es exactamente el remedio del N+1 de la [§5](#5--el-problema-n1).

Las cascadas siguen la misma lógica de propiedad, y no todas la llevan:

| Lleva `cascade="all, delete-orphan"` | No la lleva |
|---|---|
| Lo que el padre **posee**: las categorías, buzones, métodos de pago, compras, presupuestos y reglas de un `Usuario`; los renglones de una `Compra`; los comprobantes y transferencias de una `CuentaCorreo`. | Lo que el padre solo **referencia**: `Comercio.compras` (catálogo compartido: borrar un comercio no puede borrar el gasto de nadie), `MetodoPago.compras` (dar de baja una tarjeta no borra lo que se pagó con ella), `Categoria.lineas` y `CategoriaEstandar.categorias`. |

`Compra.lineas` además usa `passive_deletes=True`: el `ON DELETE CASCADE` ya lo hace la base, y sin
esa bandera SQLAlchemy cargaría los renglones solo para borrarlos uno por uno -que es el mismo N+1
por la puerta de atrás.

### 2.3 · Estado del mapeo frente al esquema del Laboratorio 2

Una diferencia que conviene declarar en vez de esconder, porque es lo primero que rompería un
`ddl-auto=validate` contra Flyway:

**El esquema que migra Flyway y el esquema que usa la aplicación en ejecución son dos linajes
distintos.**

| | Flyway (`db/postgres/migrations/`) | Aplicación (`Base.metadata` + `db/postgres/esquema-aplicacion/`) |
|---|---|---|
| Tablas | 12 | 14 |
| Quién lo crea | `flyway migrate`, `V1`…`V5` | `Base.metadata.create_all()` más scripts idempotentes `001`…`005` |
| Falta ahí | — | `comercio_categoria_sugerida` y `transferencia_sinpe` no existen en las migraciones `V1`…`V5` |

Las dos entidades que faltan nacieron después del Laboratorio 2, con las funcionalidades
adelantadas (sugerencia de categoría por comercio, y transferencias SINPE recibidas). Los scripts
de `db/postgres/esquema-aplicacion/` las crearon sobre la base viva porque `create_all()` crea
tablas nuevas pero nunca altera una que ya existía.

**Consecuencia:** la aplicación **crea** su esquema en vez de **validarlo** contra el de Flyway. La
validación en sí ya existe y corre en el CI -`test_el_mapeo_calza_con_el_esquema_que_hay_en_la_base`
compara tabla por tabla y columna por columna contra el `Inspector` de una base real, que es lo que
hace `ddl-auto=validate`. Lo que falta es que el esquema contra el que valida venga de Flyway y no
del propio mapeo; queda anotado en la [§7](#7--lo-que-queda-abierto).

---

## 3 · Repositorios con generalización

### 3.1 · El repositorio base

[`BaseRepository`](../src/app/data/repositories/base_repository.py) es genérico sobre la entidad,
con la sintaxis de parámetros de tipo de Python 3.12:

```python
class BaseRepository[TEntidad: Base]:
    def __init__(self, sesion: Session, modelo: type[TEntidad]) -> None: ...
    def agregar(self, entidad: TEntidad) -> TEntidad: ...
    def obtener_por_id(self, identificador: int) -> TEntidad | None: ...
    def listar(self) -> list[TEntidad]: ...
```

`agregar` hace `flush` pero no `commit`: el `flush` es lo que le da su `id` a la entidad para que el
servicio pueda seguir trabajando con ella dentro de la misma transacción, sin cerrarla.

El acotamiento `[TEntidad: Base]` es lo que hace que `CompraRepository.obtener_por_id` devuelva
`Compra | None` y no `Base | None`, sin que ninguna subclase tenga que redeclarar el método.

### 3.2 · Los repositorios específicos

Catorce, uno por agregado relacional. Cada uno hereda el CRUD y agrega solo lo suyo:

| Repositorio | Entidad | Consultas propias |
|---|---|---|
| `UsuarioRepository` | `Usuario` | `buscar_por_correo`, `buscar_por_google_id` |
| `CategoriaRepository` | `Categoria` | `buscar_por_nombre`, `obtener_de_usuario`, `listar_activas_de_usuario` |
| `CategoriaEstandarRepository` | `CategoriaEstandar` | `listar_ordenadas`, `buscar_por_codigo` |
| `CuentaCorreoRepository` | `CuentaCorreo` | `buscar_por_direccion`, `obtener_de_usuario`, `listar_de_usuario` |
| `ComercioRepository` | `Comercio` | `buscar_por_nombre_normalizado` |
| `ComercioCategoriaRepository` | `ComercioCategoriaSugerida` | `buscar` |
| `MetodoPagoRepository` | `MetodoPago` | `buscar_por_ultimos_cuatro`, `buscar_por_alias`, `listar_de_usuario`, `obtener_de_usuario` |
| `CompraRepository` | `Compra` | `obtener_de_usuario`, `obtener_detallada_de_usuario`, `listar_de_usuario`, `gasto_por_categoria` |
| `LineaCompraRepository` | `LineaCompra` | `listar_de_compra`, `listar_sin_categoria_de_comercio` |
| `ComprobanteRepository` | `Comprobante` | `listar_de_cuenta`, `mensajes_ya_sincronizados` |
| `TransferenciaSinpeRepository` | `TransferenciaSinpe` | `listar_de_cuenta`, `mensajes_ya_sincronizados` |
| `PresupuestoRepository` | `Presupuesto` | `buscar`, `listar_del_periodo`, `obtener_de_usuario` |
| `ReglaCategorizacionRepository` | `ReglaCategorizacion` | `listar_activas_ordenadas`, `listar_de_usuario`, `buscar_por_nombre`, `buscar_por_prioridad`, `obtener_de_usuario`, `prioridad_siguiente` |
| `TipoCambioRepository` | `TipoCambio` | `buscar`, `guardar_tasa` |

Un patrón se repite a propósito en casi todos: **`obtener_de_usuario(id, usuario_id)` en vez de
`obtener_por_id(id)`**. El aislamiento entre cuentas se sostiene en la capa de datos, no en la de
negocio: si una consulta olvidara el filtro por titular, ninguna capa de arriba podría darse
cuenta de que devolvió el dato de otra persona.

### 3.3 · El repositorio del subdominio documental

[`BitacoraRepository`](../src/app/data/repositories/bitacora_repository.py) es el acceso a la
colección `bitacora_compras` de MongoDB. Expone cuatro operaciones -`disponible`,
`agregar_evento`, `eventos_de`, `cantidad_de_eventos`- y es el único lugar del sistema que importa
PyMongo aparte del cliente compartido.

**Por qué no hereda de `BaseRepository`.** El genérico está parametrizado sobre una entidad de
SQLAlchemy y su contrato -`agregar` con `flush` sin confirmar- es el de una sesión transaccional.
Mongo acá no tiene ni sesión ni transacción: cada escritura es un `update_one` con `upsert` que se
resuelve sola. Forzar la misma firma habría obligado a implementar métodos que no significan nada
de este lado -un `agregar` que no puede participar del `commit` del servicio sería una mentira.
Comparten la **posición** en la arquitectura, no la implementación.

**La división con el servicio.** `BitacoraComprasService` decide *qué* se registra: valida el tipo
contra el vocabulario cerrado de 13 eventos, arma el documento con su actor y su número de
secuencia. El repositorio sabe *cómo* se guarda. Antes de esta separación, el servicio hablaba
PyMongo directamente y era el único acceso a datos del sistema que vivía en `business/`.

**La política de fallo.** Ningún método del repositorio propaga un `PyMongoError`: devuelven
`False` o `None`, y lo dejan en el log. Es la traducción, en el contrato del repositorio, de lo que
decide [ADR-002](adr/ADR-002-subdominio-documental-en-mongodb.md) -la bitácora **explica** lo que
pasó, no lo **decide**. Que Mongo esté caído no puede revertir una compra que PostgreSQL ya
confirmó.

---

## 4 · Consultas de negocio

Cuatro consultas con nombre propio: **dos estáticas y dos construidas dinámicamente**. El SQL de
abajo es el que **SQLAlchemy genera de verdad** en dialecto PostgreSQL, no una transcripción a
mano; los `%(nombre)s` son los parámetros que el driver enlaza aparte -nunca interpolación de
texto, que es lo que evita la inyección de SQL.

### 4.1 · Estática · Renglones sin categoría de un comercio

`LineaCompraRepository.listar_sin_categoria_de_comercio(usuario_id, comercio_id)`

**Qué responde:** cuando el titular le asigna por fin una categoría a un comercio, ¿qué compras ya
conciliadas quedaron huérfanas de categoría por haber entrado antes de esa asignación? Es lo que
hace que «corregir crea la regla» también corrija el pasado y no solo lo que viene.

```sql
SELECT linea_compra.id, linea_compra.compra_id, linea_compra.categoria_id,
       linea_compra.descripcion, linea_compra.cantidad, linea_compra.precio_unitario,
       linea_compra.descuento, linea_compra.exento_impuesto, linea_compra.subtotal,
       linea_compra.categorizada_automaticamente,
       compra.id AS id_1, compra.usuario_id, compra.comercio_id, ...
FROM linea_compra JOIN compra ON linea_compra.compra_id = compra.id
WHERE compra.usuario_id = %(usuario_id_1)s
  AND compra.comercio_id = %(comercio_id_1)s
  AND linea_compra.categoria_id IS NULL
```

Un `JOIN` real, no dos consultas: el filtro de titular vive en `compra`, pero lo que se quiere
traer son los renglones. Devuelve la tupla `(LineaCompra, Compra)` porque quien la llama necesita
las dos -el renglón para corregirlo, la compra para recalcular su estado de revisión.

### 4.2 · Estática · Reglas activas en orden de prioridad

`ReglaCategorizacionRepository.listar_activas_ordenadas(usuario_id)`

**Qué responde:** ¿en qué orden hay que evaluar las reglas del titular al categorizar una compra?
El orden no es cosmético: la primera regla que casa es la que gana, así que `ORDER BY prioridad` es
parte de la regla de negocio, no de la presentación.

```sql
SELECT regla_categorizacion.id, regla_categorizacion.usuario_id,
       regla_categorizacion.categoria_destino_id, regla_categorizacion.nombre,
       regla_categorizacion.campo, regla_categorizacion.patron,
       regla_categorizacion.prioridad, regla_categorizacion.activa,
       regla_categorizacion.veces_aplicada
FROM regla_categorizacion
WHERE regla_categorizacion.usuario_id = %(usuario_id_1)s
  AND regla_categorizacion.activa IS true
ORDER BY regla_categorizacion.prioridad
```

### 4.3 · Dinámica · Compras del titular, con filtro opcional de revisión

`CompraRepository.listar_de_usuario(usuario_id, requiere_revision=None, limite=50)`

**Qué responde:** el historial de compras, o solo las que quedaron marcadas para revisar. Es el
equivalente del patrón *Specification*: la consulta se arma por partes según los filtros que
lleguen, y el `WHERE` cambia de forma.

```python
consulta = select(Compra).options(*self._relaciones_del_detalle())
consulta = consulta.where(Compra.usuario_id == usuario_id)
if requiere_revision is not None:
    consulta = consulta.where(Compra.requiere_revision.is_(requiere_revision))
consulta = consulta.order_by(Compra.fecha.desc(), Compra.id.desc()).limit(limite)
```

Con `requiere_revision=True` -la bandeja de pendientes- aparece un `AND` que con `None` no está:

```sql
SELECT compra.id, compra.usuario_id, ... , comercio_1.id AS id_1, comercio_1.nombre, ...
FROM compra
LEFT OUTER JOIN comercio AS comercio_1 ON comercio_1.id = compra.comercio_id
LEFT OUTER JOIN metodo_pago AS metodo_pago_1 ON metodo_pago_1.id = compra.metodo_pago_id
WHERE compra.usuario_id = %(usuario_id_1)s
  AND compra.requiere_revision IS true
ORDER BY compra.fecha DESC, compra.id DESC
LIMIT %(param_1)s
```

Lo que se gana es que el filtro lo hace la base y no Python: sin él habría que traer el historial
completo para descartar la mayoría en memoria. Los `LEFT OUTER JOIN` son la carga ansiosa de la
[§5.3](#53--la-corrección).

### 4.4 · Dinámica y agregada · Gasto por categoría del mes

`CompraRepository.gasto_por_categoria(usuario_id, anio, mes, categoria_ids=None,
metodo_pago_id=None, incluir_sin_categoria=True)`

**Qué responde:** ¿en qué se le fue el mes al titular? Es la única consulta agregada del sistema:
la base suma y agrupa, en vez de traer los renglones del mes para sumarlos en Python. Y es la más
dinámica de las cuatro -tres filtros opcionales que se combinan, el equivalente de componer varias
*Specifications*.

Con el filtro de método de pago puesto:

```sql
SELECT linea_compra.categoria_id,
       coalesce(categoria.nombre, %(coalesce_1)s) AS categoria_nombre,
       sum(linea_compra.subtotal * compra.tipo_cambio_aplicado) AS total,
       count(linea_compra.id) AS cantidad
FROM linea_compra
JOIN compra ON linea_compra.compra_id = compra.id
LEFT OUTER JOIN categoria ON linea_compra.categoria_id = categoria.id
WHERE compra.usuario_id = %(usuario_id_1)s
  AND EXTRACT(year FROM compra.fecha) = %(param_1)s
  AND EXTRACT(month FROM compra.fecha) = %(param_2)s
  AND compra.estado != %(estado_1)s
  AND compra.metodo_pago_id = %(metodo_pago_id_1)s
GROUP BY linea_compra.categoria_id, categoria.nombre
ORDER BY sum(linea_compra.subtotal * compra.tipo_cambio_aplicado) DESC
```

Cuatro decisiones que hay que poder defender de esta consulta:

1. **Suma renglones, no compras.** La categoría vive en `LineaCompra`, no en `Compra`. Sumar
   `Compra.total` agrupando por categoría contaría una compra desglosada en dos categorías
   completa en cada una de las dos.
2. **Multiplica por `tipo_cambio_aplicado`.** `LineaCompra.subtotal` está en la moneda de su
   compra: sumar renglones en dólares y en colones daría un número sin significado. La tasa es la
   que regía el día de la compra y quedó congelada en ella, no la de hoy.
3. **`LEFT OUTER JOIN` a `categoria` y `coalesce`.** Los renglones sin clasificar salen en su
   propia fila, «Sin categoria». No es un caso borde: es justamente el número que le dice al
   titular cuánto de su mes todavía no tiene categoría.
4. **`EXTRACT` en vez de un rango de fechas.** El mes es el periodo natural del dominio -el
   presupuesto es mensual- y así la consulta dice lo que significa sin obligar a quien la lee a
   calcular el último día del mes.

Y las compras anuladas quedan fuera (`estado != ANULADA`): siguen en la base como historial, pero
por definición no son gasto.

---

## 5 · El problema N+1

### 5.1 · Dónde estaba

En [`CompraService.listar_del_titular`](../src/app/business/services/compra_service.py) -la que
responde `GET /api/compras`.

La consulta de compras era una sola y estaba bien. El problema era lo que venía después: por
**cada** compra devuelta, `_detallar` resolvía a mano los nombres que la entidad solo tiene como
ids sueltos, y cada resolución era su propia consulta.

```python
compras = self.compras.listar_de_usuario(usuario_id, requiere_revision, limite)  # 1 consulta
return [self._detallar(compra) for compra in compras]  # 4 por compra


def _detallar(self, compra: Compra) -> CompraDetallada:
    comercio = self.comercios.obtener_por_id(compra.comercio_id)  # +1
    metodo_pago = self.metodos_pago.obtener_por_id(compra.metodo_pago_id)  # +1
    lineas = self.lineas.listar_de_compra(compra.id)  # +1
    categoria = self.categorias.obtener_por_id(categoria_id)  # +1
```

La causa de raíz: **`Compra` no tenía relaciones mapeadas**, así que el servicio hacía a mano el
trabajo que le correspondía al ORM -y lo hacía de la peor manera posible, una fila a la vez.

### 5.2 · La evidencia, medida

Contando las sentencias `SELECT` que llegan al motor con un *listener* de
`before_cursor_execute`:

| Compras listadas | Antes | Después |
|---|---|---|
| 5 | **21** | **2** |
| 50 *(el `limite` por defecto de la pantalla)* | **201** | **2** |

El patrón era exactamente `1 + 4N`. Las 200 consultas de la segunda fila eran cuatro sentencias
que se repetían idénticas salvo el parámetro:

```
  1. SELECT compra.id, compra.usuario_id, compra.comercio_id, ... FROM compra WHERE ...
  2. SELECT comercio.id AS comercio_id, comercio.nombre, ... FROM comercio WHERE comercio.id = ?
  3. SELECT metodo_pago.id AS metodo_pago_id, ... FROM metodo_pago WHERE metodo_pago.id = ?
  4. SELECT linea_compra.id, linea_compra.compra_id, ... FROM linea_compra WHERE compra_id = ?
  5. SELECT categoria.id AS categoria_id, ... FROM categoria WHERE categoria.id = ?
  6. SELECT comercio.id AS comercio_id, ...          ← empieza la segunda compra
  ...
 21. SELECT categoria.id AS categoria_id, ...        ← termina la quinta compra
```

### 5.3 · La corrección

Dos cambios. Primero, las relaciones que le faltaban a `Compra` ([§2.1](#21--las-entidades-y-sus-relaciones)).
Segundo, pedirlas **en la consulta que sí las va a usar**:

```python
@staticmethod
def _relaciones_del_detalle():
    return (
        joinedload(Compra.comercio),
        joinedload(Compra.metodo_pago),
        selectinload(Compra.lineas).joinedload(LineaCompra.categoria),
    )
```

Y `_detallar` deja de consultar: pasa a ser puro acceso a atributos sobre lo ya cargado. El
servicio, que recibía seis repositorios para resolver ids a mano, ahora recibe **uno**.

Por qué cada estrategia:

- **`joinedload` para los `*-a-uno`** (comercio, método de pago): un `LEFT OUTER JOIN` en la misma
  consulta, sin costo de filas extra porque cada compra tiene a lo sumo uno de cada.
- **`selectinload` para la colección de renglones.** Con `joinedload` sobre una colección, el
  `LIMIT 50` se aplicaría a las **filas del producto cartesiano** y no a las compras: una compra
  con tres renglones se comería tres lugares de la página. `selectinload` los trae en una segunda
  consulta con un solo `WHERE compra_id IN (...)`. De ahí que el resultado sean 2 consultas y no 1.
- **`LEFT OUTER JOIN` y no `JOIN`.** `metodo_pago_id` es nulo cuando la conciliación no logró
  emparejar la tarjeta, y esas son exactamente las compras que el titular tiene que corregir. Con
  un `JOIN` interno desaparecerían de la lista.

**La corrección está fijada por pruebas**, no solo documentada: un N+1 no rompe nada -la pantalla
devuelve los mismos datos con 2 consultas que con 201, solo que más lento- así que sin una prueba
que cuente, se deshace sola la próxima vez que alguien agregue un campo al detalle y lo resuelva
con un `obtener_por_id` dentro del bucle. Ver
[`tests/test_n_mas_1.py`](../tests/test_n_mas_1.py), y su versión contra PostgreSQL real en
[`tests/integracion/test_consultas_postgres.py`](../tests/integracion/test_consultas_postgres.py).

---

## 6 · Cómo se prueba

Dos suites, con criterios distintos de qué va en cada una.

### 6.1 · Sobre SQLite en memoria — `tests/` · 40 pruebas

La fixture `sesion` de [`tests/conftest.py`](../tests/conftest.py) crea el esquema con
`Base.metadata.create_all()` y lo destruye al terminar, con `StaticPool` para que todas las
conexiones compartan la misma base en memoria. No tocan ningún archivo ni necesitan
infraestructura, y cada prueba arranca con la base vacía.

Eso las hace rápidas, y es lo correcto para probar reglas de negocio y el conteo de consultas.

### 6.2 · Sobre PostgreSQL real — `tests/integracion/` · 10 pruebas

Lo que la suite anterior **no** puede probar es la base. SQLite guarda `NUMERIC` como punto
flotante, ignora el largo declarado de un `VARCHAR`, y no aplica `ON DELETE CASCADE` salvo que se
encienda un `PRAGMA` que la fixture no enciende. Ya pasó una vez: un `StringDataRightTruncation` al
vincular Outlook (commit `32deefc`) que la suite en verde no vio.

Testcontainers levanta un `postgres:16-alpine` **una vez por sesión** de pytest y lo apaga al
terminar; cada prueba corre dentro de su propia transacción, que se revierte. Si no hay Docker
disponible, las pruebas **se saltan** en vez de fallar.

```bash
pytest -m integracion
```

El criterio para que una prueba viva ahí: **si SQLite la puede probar igual de bien, no justifica
levantar un contenedor.**

| Prueba | Qué verifica que SQLite no puede |
|---|---|
| `test_borrar_una_compra_arrastra_sus_renglones` | El `ON DELETE CASCADE` real, del que depende el `passive_deletes` de `Compra.lineas` |
| `test_numeric_conserva_los_centimos_sin_error_de_punto_flotante` | `NUMERIC(14,2)` como decimal exacto, incluido el `SUM` que hace la base |
| `test_una_cadena_mas_larga_que_su_columna_es_rechazada` | El largo de los `VARCHAR` -la regresión del commit `32deefc` |
| `test_el_unique_por_titular_y_nombre_rechaza_la_categoria_duplicada` | `uq_categoria_usuario_nombre` aplicado por el motor, no por el servicio |
| `test_una_transaccion_fallida_no_deja_nada_a_medias` | El `ROLLBACK` real del que depende la conciliación en cinco tablas |
| `test_el_mapeo_calza_con_el_esquema_que_hay_en_la_base` | **El equivalente del `ddl-auto=validate`**: mapeo contra `Inspector`, tabla por tabla y columna por columna |
| `test_las_llaves_foraneas_del_mapeo_existen_en_la_base` | Que las 20 relaciones tengan su `FOREIGN KEY` de verdad detrás |
| `test_el_gasto_por_categoria_suma_igual_en_postgres` | `EXTRACT`, `SUM` sobre `NUMERIC` y `GROUP BY` con la aritmética decimal real |
| `test_el_n_mas_1_sigue_corregido_contra_postgres` | Que la corrección sean 2 consultas también acá, y que el SQL lleve `LEFT OUTER JOIN` |
| `test_la_lista_conserva_las_compras_sin_metodo_de_pago` | Que el `outerjoin` no esconda justo las compras a revisar |

Las dos suites corren en el CI, en pasos separados
([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)). El runner de GitHub Actions ya trae
Docker, así que el contenedor lo administra la propia prueba: no hace falta declarar ningún
`services:` en el workflow.

---

## 7 · Lo que queda abierto

Una sola cosa, y está acotada: **que el esquema contra el que se valida venga de Flyway.**

La validación ya existe y corre en el CI, pero hoy compara el mapeo contra un esquema que el propio
mapeo creó -así que por construcción coincide. Cerrarlo del todo pide dos cosas:

1. Migraciones `V6` y `V7` que lleven `comercio_categoria_sugerida` y `transferencia_sinpe` al
   linaje de Flyway, para que las dos numeraciones vuelvan a describir la misma base
   ([§2.3](#23--estado-del-mapeo-frente-al-esquema-del-laboratorio-2)).
2. Que la fixture de integración aplique esas migraciones sobre el contenedor en vez de llamar a
   `create_all()`. La prueba de validación no cambia una línea: recién ahí empieza a poder fallar,
   que es cuando de verdad sirve.

---

## Documentos relacionados

| Documento | Qué contiene |
|---|---|
| [Modelo de datos](modelo-de-datos.md) | **Laboratorio 2.** El esquema relacional, su normalización, sus restricciones e índices justificados, y el subdominio de MongoDB. |
| [Arquitectura](arquitectura.md) | Capas, recorrido de una petición, modelo entidad-relación y despliegue previsto. |
| [Propuesta de Dominio](propuesta-dominio.md) | El negocio, los actores, las entidades y los dos procesos con sus reglas. |
| [ADR-001 · Elección del stack](adr/ADR-001-eleccion-del-stack.md) | Por qué SQLAlchemy y no JPA/Hibernate, qué se descartó y qué cuesta. |
| [ADR-002 · Subdominio documental](adr/ADR-002-subdominio-documental-en-mongodb.md) | Por qué la trazabilidad de la compra va en MongoDB. |
| [ADR-003 · Flyway para las migraciones](adr/ADR-003-flyway-para-las-migraciones.md) | Por qué Flyway en un contenedor en lugar de Alembic. |

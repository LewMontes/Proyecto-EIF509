-- ============================================================================
--  V5 · Índices de consulta
--  Gastonomo · EIF509 · Laboratorio 2
--
--  Los índices que nacen de una restricción (PRIMARY KEY, UNIQUE) ya quedaron
--  creados junto a su tabla en V1–V4: son parte de la definición del dato. Esta
--  migración agrega los que existen SOLO por rendimiento, y va aparte
--  precisamente por eso: un índice de rendimiento se justifica contra una
--  consulta concreta, se mide, y se puede quitar sin cambiar el significado del
--  modelo. Cada bloque de abajo nombra la consulta que le da razón de ser.
--
--  Un índice no es gratis: ocupa espacio y encarece cada INSERT y UPDATE de su
--  tabla. Por eso no hay uno por columna, sino uno por patrón de consulta real.
-- ============================================================================


-- ----------------------------------------------------------------------------
--  1 · Lista de gastos del titular
--
--      SELECT ... FROM compra
--       WHERE usuario_id = :u AND fecha BETWEEN :desde AND :hasta
--       ORDER BY fecha DESC;
--
--  Es la consulta más ejecutada del sistema: la pantalla principal. El orden
--  descendente de la fecha dentro del índice permite que el filtro por titular,
--  el rango de fechas y el ORDER BY se resuelvan en un solo recorrido, sin
--  ordenar en memoria.
-- ----------------------------------------------------------------------------
CREATE INDEX ix_compra_usuario_fecha ON compra (usuario_id, fecha DESC);


-- ----------------------------------------------------------------------------
--  2 · Reporte de gasto por categoría
--
--      SELECT l.categoria_id, SUM(l.subtotal) FROM linea_compra l
--        JOIN compra c ON c.id = l.compra_id
--       WHERE c.usuario_id = :u AND c.fecha BETWEEN :desde AND :hasta
--       GROUP BY l.categoria_id;
--
--  El índice de la compra lo aporta el punto 1. Este cubre el lado del renglón:
--  con subtotal incluido (INCLUDE), la suma se calcula leyendo solo el índice,
--  sin ir a buscar la fila completa en la tabla.
-- ----------------------------------------------------------------------------
CREATE INDEX ix_linea_compra_categoria
    ON linea_compra (categoria_id)
    INCLUDE (subtotal)
    WHERE categoria_id IS NOT NULL;


-- ----------------------------------------------------------------------------
--  3 · Reportes de gasto por comercio y por método de pago
--
--      SELECT comercio_id, SUM(total_moneda_base) FROM compra
--       WHERE usuario_id = :u AND fecha BETWEEN :desde AND :hasta
--       GROUP BY comercio_id;   -- (y su gemelo por metodo_pago_id)
--
--  Los dos reportes agrupan sobre la misma tabla ya filtrada por titular y
--  fecha. Se indexan por separado porque el criterio de agrupación es el que
--  ordena las filas dentro del índice, y un índice solo puede tener un orden.
-- ----------------------------------------------------------------------------
CREATE INDEX ix_compra_usuario_comercio
    ON compra (usuario_id, comercio_id, fecha DESC);

CREATE INDEX ix_compra_usuario_metodo_pago
    ON compra (usuario_id, metodo_pago_id, fecha DESC)
    WHERE metodo_pago_id IS NOT NULL;


-- ----------------------------------------------------------------------------
--  4 · Cola de trabajo del servicio de ingesta
--
--      SELECT ... FROM comprobante
--       WHERE estado IN ('RECIBIDO', 'PARSEADO')
--       ORDER BY recibido_en;
--
--  Índice PARCIAL: el servicio de ingesta solo mira los comprobantes que aún
--  tiene pendientes. Los PROCESADO son la inmensa mayoría de la tabla y crecen
--  sin parar, pero jamás aparecen en esta consulta, así que no tienen por qué
--  ocupar espacio en el índice ni encarecer su mantenimiento.
-- ----------------------------------------------------------------------------
CREATE INDEX ix_comprobante_pendientes
    ON comprobante (recibido_en)
    WHERE estado IN ('RECIBIDO', 'PARSEADO');


-- ----------------------------------------------------------------------------
--  5 · Bandeja de revisión manual del titular
--
--      SELECT ... FROM compra WHERE usuario_id = :u AND requiere_revision;
--
--  Parcial por la misma razón: lo normal es que una compra NO requiera
--  revisión, así que el índice solo guarda la excepción.
-- ----------------------------------------------------------------------------
CREATE INDEX ix_compra_revision_pendiente
    ON compra (usuario_id, fecha DESC)
    WHERE requiere_revision;


-- ----------------------------------------------------------------------------
--  6 · Catálogo de categorías activas del titular
--
--      SELECT ... FROM categoria WHERE usuario_id = :u AND activa;
--
--  Una categoría con gasto asociado no se borra: se desactiva, para no romper
--  el histórico. Con el tiempo la tabla acumula categorías inactivas que ningún
--  selector vuelve a mostrar; el índice parcial las deja fuera.
-- ----------------------------------------------------------------------------
CREATE INDEX ix_categoria_usuario_activa
    ON categoria (usuario_id, nombre)
    WHERE activa;


-- ----------------------------------------------------------------------------
--  7 · Resolución difusa del nombre del comercio
--
--      SELECT id, nombre_normalizado FROM comercio
--       WHERE nombre_normalizado % :nombre_del_correo
--       ORDER BY similarity(nombre_normalizado, :nombre_del_correo) DESC
--       LIMIT 5;
--
--  El operador % ('se parece a') es el que resuelve el índice GIN de trigramas;
--  el ORDER BY solo tiene que ordenar el puñado de filas que sobrevivió al
--  filtro, no el catálogo entero.
--
--  El nombre que llega en un correo casi nunca coincide letra por letra con el
--  del catálogo: 'AUTOMERCADO #12 SAN PEDRO' contra 'AUTOMERCADO'. La igualdad
--  exacta ya la resuelve el índice de uq_comercio_nombre_normalizado; cuando
--  falla, la ingesta busca el parecido más cercano. Sin un índice de trigramas
--  eso obliga a comparar contra TODAS las filas del catálogo en cada correo que
--  entra.
--
--  pg_trgm viene con la distribución estándar de PostgreSQL (módulo contrib),
--  así que la extensión no agrega ninguna dependencia externa al despliegue.
-- ----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX ix_comercio_nombre_trigramas
    ON comercio USING gin (nombre_normalizado gin_trgm_ops);

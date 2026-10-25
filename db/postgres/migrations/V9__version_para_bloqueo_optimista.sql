-- ============================================================================
--  V9 · Versión del presupuesto para el bloqueo optimista
--  Gastonomo · EIF509 · Laboratorio 7
--
--  `presupuesto.monto_consumido` es la única fila del sistema que varios
--  caminos leen, suman y vuelven a escribir sobre el mismo dato:
--
--    · el registro manual de una compra        (Proceso 1)
--    · la conciliación de un comprobante        (Proceso 2, llega solo por correo)
--    · la anulación y la corrección de compras  (devuelven o recalculan monto)
--    · el PUT que corrige el límite y el umbral
--
--  Dos de esos que se confirman a la vez sobre la misma categoría y mes leen el
--  mismo consumido, y el segundo en escribir pisa al primero: un gasto real
--  desaparece del presupuesto sin ningún error (lost update).
--
--  La columna `version` es el `@Version` de JPA. El mapeo la declara como
--  `version_id_col`, así que cada UPDATE que hace la aplicación es:
--
--      UPDATE presupuesto SET ..., version = :v + 1
--       WHERE id = :id AND version = :v;
--
--  Si otra transacción ya la subió, el UPDATE no afecta ninguna fila, el ORM lo
--  detecta (StaleDataError) y la API responde 409. Sin candados: nadie espera.
--
--  Lo que NO cambia: ninguna columna existente cambia de tipo ni se borra.
-- ============================================================================

--  El DEFAULT 1 deja a todas las filas que ya existían -y a las del seed
--  afterMigrate- con una versión válida sin un UPDATE aparte. La aplicación no
--  depende del DEFAULT: SQLAlchemy pone el 1 al insertar.
ALTER TABLE presupuesto
    ADD COLUMN version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE presupuesto
    ADD CONSTRAINT ck_presupuesto_version_positiva CHECK (version >= 1);

COMMENT ON COLUMN presupuesto.version IS
    'Bloqueo optimista: sube en cada UPDATE. Un UPDATE con una versión vieja no toca ninguna fila y la API responde 409.';

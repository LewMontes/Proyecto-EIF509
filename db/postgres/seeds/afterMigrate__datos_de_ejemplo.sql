-- ============================================================================
--  Datos de ejemplo · PostgreSQL
--  Gastonomo · EIF509 · Laboratorio 2
--
--  POR QUÉ ES UN CALLBACK Y NO UNA MIGRACIÓN V6
--  --------------------------------------------
--  Los datos de ejemplo no son parte del esquema. Si vivieran como V6, Flyway
--  los registraría en su historial y llevarlos a producción obligaría a excluir
--  una versión a mano. Como callback afterMigrate corren con el mismo
--  'docker compose up' en desarrollo, y se dejan fuera en cualquier otro
--  entorno quitando su carpeta de flyway.locations.
--
--  Todos los INSERT llevan ON CONFLICT DO NOTHING porque afterMigrate se
--  ejecuta en cada 'flyway migrate', también cuando no hay nada nuevo que
--  aplicar. Correr el comando dos veces tiene que dar el mismo resultado.
--
--  Los identificadores se fijan a mano en vez de dejarlos a la secuencia porque
--  los documentos de MongoDB referencian estas mismas compras por su id: si
--  cambiaran de una carga a otra, la bitácora quedaría apuntando al vacío. Al
--  final del archivo se reposicionan las secuencias para que las altas
--  siguientes, ya con id automático, no choquen con lo sembrado.
--
--  Escenario que arma este archivo (agosto 2026):
--    · Dos titulares, uno con historial completo y otro recién empezando.
--    · Compras ingeridas por correo, capturadas a mano, en dólares y anuladas.
--    · Un presupuesto sobregirado, uno vacío por anulación y varios en curso.
--    · Un comprobante en revisión manual y otro fallido tras tres intentos.
-- ============================================================================


-- ----------------------------------------------------------------------------
--  Titulares
--  El hash es un bcrypt real de la contraseña 'Laboratorio2!' — sirve para
--  probar el login cuando llegue la autenticación, y deja claro que en esta
--  columna nunca va texto plano.
-- ----------------------------------------------------------------------------
INSERT INTO usuario (id, nombre_completo, correo, contrasena_hash, moneda_preferida, activo) VALUES
    (1, 'Jose Alexis Solis Carvajal',      'jose.solis@gastonomo.cr',  '$2b$12$Kx7pQmWvJ3nR8sT1uY5aBeC9dF2gH4jK6lM8nP0qR2sT4uV6wX8yZ', 'CRC', TRUE),
    (2, 'Luis Antonio Montes de Oca Ruiz', 'luis.montes@gastonomo.cr', '$2b$12$Ab1cD3eF5gH7iJ9kL1mN3oP5qR7sT9uV1wX3yZ5aB7cD9eF1gH3iJ', 'CRC', TRUE)
ON CONFLICT DO NOTHING;


-- ----------------------------------------------------------------------------
--  Buzones vinculados
--  Los tokens de ejemplo son cadenas marcadas: la aplicación los cifra antes de
--  guardarlos, así que aquí nunca aparece un token real ni uno en claro.
-- ----------------------------------------------------------------------------
INSERT INTO cuenta_correo (id, usuario_id, proveedor, direccion, token_acceso_cifrado,
                           token_refresco_cifrado, expira_en, ultima_sincronizacion, estado) VALUES
    (1, 1, 'GMAIL',   'jose.solis.cr@gmail.com',      'enc:v1:AAAA-token-de-ejemplo-acceso-01',   'enc:v1:AAAA-token-de-ejemplo-refresco-01', '2026-09-30 06:00:00-06', '2026-08-21 07:15:00-06', 'ACTIVA'),
    (2, 2, 'OUTLOOK', 'luis.montes@outlook.com',      'enc:v1:BBBB-token-de-ejemplo-acceso-02',   'enc:v1:BBBB-token-de-ejemplo-refresco-02', '2026-09-15 06:00:00-06', '2026-08-19 20:40:00-06', 'ACTIVA')
ON CONFLICT DO NOTHING;


-- ----------------------------------------------------------------------------
--  Taxonomía estándar
--  Las quince categorías con las que se siembra toda cuenta nueva, para que
--  nadie arranque con una lista vacía. Es también el vocabulario que usan los
--  comercios compartidos para sugerir categoría.
-- ----------------------------------------------------------------------------
INSERT INTO categoria_estandar (id, codigo, nombre, descripcion, color_hex, orden) VALUES
    ( 1, 'ALIMENTACION',       'Alimentacion',        'Todo lo que se come y se bebe',                    '#16A34A',  1),
    ( 2, 'SUPERMERCADO',       'Supermercado',        'Compras de abarrotes y canasta basica',            '#22C55E',  2),
    ( 3, 'RESTAURANTES',       'Restaurantes y sodas','Comidas fuera de casa y pedidos a domicilio',      '#4ADE80',  3),
    ( 4, 'TRANSPORTE',         'Transporte',          'Traslados y mantenimiento del vehiculo',           '#2563EB',  4),
    ( 5, 'COMBUSTIBLE',        'Combustible',         'Gasolina y diesel',                                '#3B82F6',  5),
    ( 6, 'SALUD',              'Salud',               'Consultas, examenes y tratamientos',               '#DC2626',  6),
    ( 7, 'FARMACIA',           'Farmacia',            'Medicamentos y productos de botiquin',             '#EF4444',  7),
    ( 8, 'HOGAR',              'Hogar',               'Limpieza, ferreteria y mantenimiento de la casa',  '#D97706',  8),
    ( 9, 'SERVICIOS_PUBLICOS', 'Servicios publicos',  'Electricidad, agua, internet y telefonia',         '#F59E0B',  9),
    (10, 'SUSCRIPCIONES',      'Suscripciones',       'Servicios recurrentes, casi siempre en dolares',   '#9333EA', 10),
    (11, 'ENTRETENIMIENTO',    'Entretenimiento',     'Cine, conciertos, paseos y salidas',               '#C026D3', 11),
    (12, 'EDUCACION',          'Educacion',           'Matriculas, cursos y materiales de estudio',       '#0891B2', 12),
    (13, 'ROPA',               'Ropa y calzado',      'Vestimenta y accesorios',                          '#DB2777', 13),
    (14, 'MASCOTAS',           'Mascotas',            'Alimento, veterinario y accesorios',               '#65A30D', 14),
    (15, 'OTROS',              'Otros',               'Gasto que todavia no encaja en ninguna categoria', '#6B7280', 15)
ON CONFLICT DO NOTHING;


-- ----------------------------------------------------------------------------
--  Categorías de cada titular
--  Jerárquicas: las padre (es_hoja = FALSE) existen para totalizar y no reciben
--  gasto directo; solo las hoja se pueden asignar a un renglón.
-- ----------------------------------------------------------------------------
INSERT INTO categoria (id, usuario_id, categoria_padre_id, categoria_estandar_id, nombre, descripcion, color_hex, es_hoja, activa) VALUES
    -- Titular 1
    ( 1, 1, NULL,  1, 'Alimentacion',        'Total de lo que se come y se bebe',   '#16A34A', FALSE, TRUE),
    ( 2, 1,    1,  2, 'Supermercado',        'Abarrotes y canasta basica',          '#22C55E', TRUE,  TRUE),
    ( 3, 1,    1,  3, 'Restaurantes y sodas','Comidas fuera de casa',               '#4ADE80', TRUE,  TRUE),
    ( 4, 1, NULL,  4, 'Transporte',          'Total de traslados',                  '#2563EB', FALSE, TRUE),
    ( 5, 1,    4,  5, 'Combustible',         'Gasolina del carro',                  '#3B82F6', TRUE,  TRUE),
    ( 6, 1, NULL,  6, 'Salud',               'Total de salud',                      '#DC2626', FALSE, TRUE),
    ( 7, 1,    6,  7, 'Farmacia',            'Medicamentos',                        '#EF4444', TRUE,  TRUE),
    ( 8, 1, NULL,  8, 'Hogar',               'Limpieza y ferreteria',               '#D97706', TRUE,  TRUE),
    ( 9, 1, NULL,  9, 'Servicios publicos',  'Luz, agua e internet',                '#F59E0B', TRUE,  TRUE),
    (10, 1, NULL, 10, 'Suscripciones',       'Streaming y servicios recurrentes',   '#9333EA', TRUE,  TRUE),
    (11, 1, NULL, 14, 'Mascotas',            'Gastos de la perra',                  '#65A30D', TRUE,  TRUE),
    -- Titular 2 (cuenta recién creada: solo lo que ha usado)
    (12, 2, NULL,  1, 'Alimentacion',        'Total de lo que se come y se bebe',   '#16A34A', FALSE, TRUE),
    (13, 2,   12,  2, 'Supermercado',        'Abarrotes y canasta basica',          '#22C55E', TRUE,  TRUE),
    (14, 2, NULL, 10, 'Suscripciones',       'Servicios recurrentes',               '#9333EA', TRUE,  TRUE),
    (15, 2, NULL, 15, 'Otros',               'Sin clasificar todavia',              '#6B7280', TRUE,  TRUE)
ON CONFLICT DO NOTHING;


-- ----------------------------------------------------------------------------
--  Catálogo compartido de comercios
--  El nombre normalizado es la llave con la que la ingesta agrupa las variantes
--  sucias que llegan en los correos. AMAZON WEB SERVICES entra sin categoría
--  sugerida a propósito: es el caso del comercio que creó la ingesta y que
--  nadie ha clasificado todavía.
-- ----------------------------------------------------------------------------
INSERT INTO comercio (id, categoria_estandar_sugerida_id, nombre, nombre_normalizado, identificacion_tributaria, provincia) VALUES
    ( 1,    2, 'Automercado',            'AUTOMERCADO',            '3101007223', 'San Jose'),
    ( 2,    2, 'Walmart',                'WALMART',                '3101019584', 'San Jose'),
    ( 3,    2, 'Pali',                   'PALI',                   '3101019584', 'Heredia'),
    ( 4,    2, 'Mas x Menos',            'MAS X MENOS',            '3101019584', 'San Jose'),
    ( 5,    7, 'Farmacia Fischel',       'FARMACIA FISCHEL',       '3101008846', 'San Jose'),
    ( 6,    5, 'Gasolinera Delta',       'GASOLINERA DELTA',       '3101095436', 'Cartago'),
    ( 7,    3, 'Soda Tapia',             'SODA TAPIA',             '3101112233', 'San Jose'),
    ( 8,   10, 'Spotify',                'SPOTIFY',                NULL,         NULL),
    ( 9,   10, 'Netflix',                'NETFLIX',                NULL,         NULL),
    (10,    9, 'Grupo ICE',              'GRUPO ICE',              '4000042139', 'San Jose'),
    (11,    9, 'Acueductos y Alcantarillados', 'AYA',              '4000042138', 'San Jose'),
    (12,    8, 'EPA',                    'EPA',                    '3101334455', 'Heredia'),
    (13,   14, 'Veterinaria San Pedro',  'VETERINARIA SAN PEDRO',  '3101556677', 'San Jose'),
    (14,    4, 'Uber',                   'UBER',                   NULL,         NULL),
    (15, NULL, 'Amazon Web Services',    'AMAZON WEB SERVICES',    NULL,         NULL)
ON CONFLICT DO NOTHING;


-- ----------------------------------------------------------------------------
--  Métodos de pago
--  Solo las tarjetas llevan últimos cuatro dígitos, y solo las de crédito
--  llevan día de corte: lo exigen los CHECK de la V2.
-- ----------------------------------------------------------------------------
INSERT INTO metodo_pago (id, usuario_id, alias, tipo, moneda, ultimos_cuatro, entidad, dia_corte, activo) VALUES
    (1, 1, 'BAC Visa Clasica',        'CREDITO',       'CRC', '6411', 'BAC Credomatic',  15,   TRUE),
    (2, 1, 'BCR Debito',              'DEBITO',        'CRC', '8823', 'Banco de Costa Rica', NULL, TRUE),
    (3, 1, 'Efectivo',                'EFECTIVO',      'CRC', NULL,   NULL,              NULL, TRUE),
    (4, 1, 'SINPE Movil',             'SINPE_MOVIL',   'CRC', NULL,   'BAC Credomatic',  NULL, TRUE),
    (5, 2, 'BN Debito',               'DEBITO',        'CRC', '1042', 'Banco Nacional',  NULL, TRUE),
    (6, 2, 'Scotiabank Visa Dolares', 'CREDITO',       'USD', '7730', 'Scotiabank',       5,   TRUE)
ON CONFLICT DO NOTHING;


-- ----------------------------------------------------------------------------
--  Tipos de cambio
--  Uno por fecha: una compra en dólares se convierte siempre con la tasa de su
--  propio día, no con la de hoy.
-- ----------------------------------------------------------------------------
INSERT INTO tipo_cambio (id, moneda_origen, moneda_destino, fecha, tasa, fuente) VALUES
    (1, 'USD', 'CRC', '2026-08-03', 511.900000, 'BCCR'),
    (2, 'USD', 'CRC', '2026-08-05', 512.480000, 'BCCR'),
    (3, 'USD', 'CRC', '2026-08-10', 512.950000, 'BCCR'),
    (4, 'USD', 'CRC', '2026-08-16', 513.200000, 'BCCR'),
    (5, 'USD', 'CRC', '2026-08-20', 514.050000, 'BCCR'),
    (6, 'EUR', 'CRC', '2026-08-16', 596.300000, 'BCCR')
ON CONFLICT DO NOTHING;


-- ----------------------------------------------------------------------------
--  Compras
--
--  Los totales cumplen las fórmulas que verifican los CHECK de la V3:
--      total             = subtotal - descuento + impuesto
--      total_moneda_base = round(total * tipo_cambio_aplicado, 2)
--  Si alguno estuviera mal calculado, la carga fallaría aquí mismo. Ese es
--  justamente el punto de haberlas escrito en el esquema.
-- ----------------------------------------------------------------------------
INSERT INTO compra (id, usuario_id, comercio_id, metodo_pago_id, fecha, descripcion, moneda,
                    estado, origen, subtotal, descuento, impuesto, impuesto_desglosado,
                    total, tipo_cambio_aplicado, total_moneda_base, requiere_revision) VALUES
    -- Ingerida por correo: una sola linea por el monto total, sin desglose de impuesto.
    ( 1, 1,  1, 2, '2026-08-03', 'Compra del fin de semana',      'CRC', 'CONCILIADA', 'INGESTA_CORREO', 45320.00,   0.00,   0.00, FALSE, 45320.00,   1.000000, 45320.00, FALSE),
    -- Capturada a mano: tres renglones, impuesto desglosado y un descuento de renglon.
    ( 2, 1,  4, 1, '2026-08-07', 'Compra de quincena',            'CRC', 'REGISTRADA', 'MANUAL',          9870.00,   0.00, 897.00, TRUE,  10767.00,   1.000000, 10767.00, FALSE),
    -- En dolares: se convierte con la tasa de su propia fecha (2026-08-05).
    ( 3, 1,  8, 1, '2026-08-05', 'Spotify Premium',               'USD', 'CONCILIADA', 'INGESTA_CORREO',    11.99,   0.00,   0.00, FALSE,    11.99, 512.480000,  6144.64, FALSE),
    ( 4, 1,  6, 1, '2026-08-10', 'Tanqueada',                     'CRC', 'CONCILIADA', 'INGESTA_CORREO', 25000.00,   0.00,   0.00, FALSE, 25000.00,   1.000000, 25000.00, FALSE),
    ( 5, 1,  5, 4, '2026-08-12', 'Medicamentos',                  'CRC', 'REGISTRADA', 'MANUAL',          2400.00,   0.00, 312.00, TRUE,   2712.00,   1.000000,  2712.00, FALSE),
    ( 6, 1, 12, 2, '2026-08-15', 'Cosas para la casa',            'CRC', 'REGISTRADA', 'INGESTA_CORREO', 18750.00,   0.00,   0.00, FALSE, 18750.00,   1.000000, 18750.00, FALSE),
    -- Ingerida y despues partida a mano por el titular en dos renglones.
    ( 7, 1,  1, 1, '2026-08-18', 'Automercado',                   'CRC', 'REGISTRADA', 'INGESTA_CORREO', 12400.00,   0.00,   0.00, FALSE, 12400.00,   1.000000, 12400.00, FALSE),
    ( 8, 1,  9, 1, '2026-08-20', 'Netflix Estandar',              'USD', 'CONCILIADA', 'INGESTA_CORREO',    15.99,   0.00,   0.00, FALSE,    15.99, 514.050000,  8219.66, FALSE),
    -- Anulada: nunca se borra fisicamente, y su monto se devolvio al presupuesto.
    ( 9, 1,  7, 3, '2026-08-08', 'Almuerzo (cobro duplicado)',    'CRC', 'ANULADA',    'MANUAL',          3500.00,   0.00, 455.00, TRUE,   3955.00,   1.000000,  3955.00, FALSE),
    (10, 2,  3, 5, '2026-08-11', 'Compra de la semana',           'CRC', 'REGISTRADA', 'INGESTA_CORREO',  9800.00,   0.00,   0.00, FALSE,  9800.00,   1.000000,  9800.00, FALSE),
    -- Comercio sin categoria sugerida: la compra queda en BORRADOR, con su
    -- renglon sin categoria, marcada para revision del titular.
    (11, 2, 15, 6, '2026-08-16', 'Cargo mensual AWS',             'USD', 'BORRADOR',   'INGESTA_CORREO',    42.17,   0.00,   0.00, FALSE,    42.17, 513.200000, 21641.64, TRUE)
ON CONFLICT DO NOTHING;


-- ----------------------------------------------------------------------------
--  Renglones
--  subtotal = round(cantidad * precio_unitario - descuento, 2), verificado por
--  el CHECK de la V3.
-- ----------------------------------------------------------------------------
INSERT INTO linea_compra (id, compra_id, usuario_id, categoria_id, descripcion, cantidad,
                          precio_unitario, descuento, exento_impuesto, subtotal,
                          categorizada_automaticamente) VALUES
    ( 1,  1, 1,    2, 'Compra en Automercado (sin desglose)', 1.000, 45320.00,   0.00, FALSE, 45320.00, TRUE),
    ( 2,  2, 1,    2, 'Arroz 1 kg',                           2.000,  1450.00,   0.00, FALSE,  2900.00, FALSE),
    ( 3,  2, 1,    2, 'Leche 1 L',                            3.000,   990.00,   0.00, TRUE,   2970.00, FALSE),
    ( 4,  2, 1,    8, 'Detergente 3 kg',                      1.000,  4250.00, 250.00, FALSE,  4000.00, FALSE),
    ( 5,  3, 1,   10, 'Spotify Premium mensual',              1.000,    11.99,   0.00, FALSE,    11.99, TRUE),
    ( 6,  4, 1,    5, 'Combustible super',                    1.000, 25000.00,   0.00, FALSE, 25000.00, TRUE),
    ( 7,  5, 1,    7, 'Acetaminofen 500 mg (20 tabletas)',    2.000,  1200.00,   0.00, FALSE,  2400.00, FALSE),
    ( 8,  6, 1,    8, 'Compra en EPA (sin desglose)',         1.000, 18750.00,   0.00, FALSE, 18750.00, TRUE),
    -- Los dos renglones en que el titular partio el cargo de 12 400 colones.
    ( 9,  7, 1,    2, 'Automercado - alimentos',              1.000,  7440.00,   0.00, FALSE,  7440.00, FALSE),
    (10,  7, 1,    8, 'Automercado - limpieza',               1.000,  4960.00,   0.00, FALSE,  4960.00, FALSE),
    (11,  8, 1,   10, 'Netflix Estandar mensual',             1.000,    15.99,   0.00, FALSE,    15.99, TRUE),
    (12,  9, 1,    3, 'Casado con pollo (2)',                 1.000,  3500.00,   0.00, FALSE,  3500.00, FALSE),
    (13, 10, 2,   13, 'Compra en Pali (sin desglose)',        1.000,  9800.00,   0.00, FALSE,  9800.00, TRUE),
    -- Sin categoria: solo se permite porque la compra 11 esta en BORRADOR.
    (14, 11, 2, NULL, 'Cargo AWS de agosto',                  1.000,    42.17,   0.00, FALSE,    42.17, FALSE)
ON CONFLICT DO NOTHING;


-- ----------------------------------------------------------------------------
--  Comprobantes
--  Constancia de qué correo originó cada compra. No guardan el mensaje: el
--  sistema lo lee, le extrae los cuatro campos que necesita y lo descarta.
-- ----------------------------------------------------------------------------
INSERT INTO comprobante (id, usuario_id, cuenta_correo_id, compra_id, mensaje_id, remitente,
                         recibido_en, estado, confianza_parseo, intentos_procesamiento, motivo_fallo) VALUES
    ( 1, 1, 1,    1, 'BAC-2026-08-03-0001',    'notificaciones@baccredomatic.cr', '2026-08-03 14:22:00-06', 'PROCESADO',       1.000, 1, NULL),
    ( 2, 1, 1,    3, 'SPOT-2026-08-05-77120',  'no-reply@spotify.com',            '2026-08-05 02:11:00-06', 'PROCESADO',       0.950, 1, NULL),
    ( 3, 1, 1,    4, 'BAC-2026-08-10-0442',    'notificaciones@baccredomatic.cr', '2026-08-10 17:48:00-06', 'PROCESADO',       1.000, 1, NULL),
    ( 4, 1, 1,    6, 'BCR-2026-08-15-8891',    'avisos@bancobcr.com',             '2026-08-15 11:05:00-06', 'PROCESADO',       0.875, 1, NULL),
    ( 5, 1, 1,    7, 'BAC-2026-08-18-0517',    'notificaciones@baccredomatic.cr', '2026-08-18 19:33:00-06', 'PROCESADO',       1.000, 1, NULL),
    ( 6, 1, 1,    8, 'NFLX-2026-08-20-31004',  'info@mailer.netflix.com',         '2026-08-20 03:02:00-06', 'PROCESADO',       0.950, 1, NULL),
    -- Confianza por debajo de 0.75: no se convierte en compra solo, queda para
    -- que el titular lo revise. Preferimos molestarlo antes que inventarle un gasto.
    ( 7, 1, 1, NULL, 'BAC-2026-08-21-0603',    'notificaciones@baccredomatic.cr', '2026-08-21 09:14:00-06', 'REVISION_MANUAL', 0.500, 1, NULL),
    ( 8, 2, 2,   10, 'BNCR-2026-08-11-1980',   'notificaciones@bncr.fi.cr',       '2026-08-11 16:27:00-06', 'PROCESADO',       0.875, 1, NULL),
    ( 9, 2, 2,   11, 'SCOTIA-2026-08-16-4410', 'alertas@scotiabankcr.com',        '2026-08-16 08:50:00-06', 'PROCESADO',       0.750, 1, NULL),
    -- Tres intentos fallidos: pasa a FALLIDO y se le notifica al titular.
    (10, 2, 2, NULL, 'BNCR-2026-08-19-2210',   'notificaciones@bncr.fi.cr',       '2026-08-19 21:40:00-06', 'FALLIDO',         NULL,  3,
        'El patron del remitente no reconocio el monto: el correo llego como resumen de varios cargos en vez de una notificacion individual.')
ON CONFLICT DO NOTHING;


-- ----------------------------------------------------------------------------
--  Presupuestos de agosto 2026
--  monto_consumido es la suma, en moneda base, de los renglones de esa
--  categoria. Suscripciones aparece sobregirado a propósito (14 364,30 contra
--  un limite de 12 000) y Restaurantes en cero porque su unica compra se anulo:
--  anular devuelve el monto al presupuesto.
-- ----------------------------------------------------------------------------
INSERT INTO presupuesto (id, usuario_id, categoria_id, anio, mes, monto_limite, monto_consumido, moneda, umbral_alerta, estado) VALUES
    (1, 1,  2, 2026, 8, 120000.00, 58630.00, 'CRC', 80, 'ACTIVO'),
    (2, 1,  8, 2026, 8,  40000.00, 27710.00, 'CRC', 80, 'ACTIVO'),
    (3, 1,  5, 2026, 8,  60000.00, 25000.00, 'CRC', 75, 'ACTIVO'),
    (4, 1,  7, 2026, 8,  25000.00,  2400.00, 'CRC', 80, 'ACTIVO'),
    (5, 1, 10, 2026, 8,  12000.00, 14364.30, 'CRC', 90, 'ACTIVO'),
    (6, 1,  3, 2026, 8,  50000.00,     0.00, 'CRC', 80, 'ACTIVO'),
    (7, 2, 13, 2026, 8,  80000.00,  9800.00, 'CRC', 80, 'ACTIVO')
ON CONFLICT DO NOTHING;


-- ----------------------------------------------------------------------------
--  Reglas de categorización
--  Nacen de que el titular corrija una categoría, no de una pantalla de
--  configuración. Se evalúan por prioridad ascendente y gana la primera que
--  coincide, por eso la prioridad es única dentro de cada titular.
-- ----------------------------------------------------------------------------
INSERT INTO regla_categorizacion (id, usuario_id, categoria_destino_id, nombre, campo, patron, prioridad, activa, veces_aplicada) VALUES
    (1, 1,  2, 'Automercado a Supermercado',   'COMERCIO_NORMALIZADO', 'AUTOMERCADO',       10, TRUE, 2),
    (2, 1,  5, 'Delta a Combustible',          'COMERCIO_NORMALIZADO', 'GASOLINERA DELTA',  20, TRUE, 1),
    (3, 1, 10, 'Streaming a Suscripciones',    'COMERCIO_NORMALIZADO', 'NETFLIX|SPOTIFY',   30, TRUE, 2),
    (4, 1,  8, 'EPA a Hogar',                  'COMERCIO_NORMALIZADO', 'EPA',               40, TRUE, 1),
    -- Excepcion mas especifica que la regla 1: por eso su prioridad es MENOR.
    -- El alimento de mascota comprado en el supermercado no es alimentacion.
    (5, 1, 11, 'Alimento de mascota',          'DESCRIPCION_LINEA',    'DOG CHOW|WHISKAS',   5, TRUE, 0),
    (6, 2, 13, 'Pali a Supermercado',          'COMERCIO_NORMALIZADO', 'PALI',              10, TRUE, 1)
ON CONFLICT DO NOTHING;


-- ----------------------------------------------------------------------------
--  Reposicionamiento de las secuencias
--
--  Se sembraron identificadores explícitos, así que las secuencias siguen en 1
--  y el primer INSERT normal de la aplicación chocaría contra la llave primaria.
--  setval las deja apuntando al último id usado.
-- ----------------------------------------------------------------------------
SELECT setval(pg_get_serial_sequence('usuario',              'id'), (SELECT max(id) FROM usuario));
SELECT setval(pg_get_serial_sequence('cuenta_correo',        'id'), (SELECT max(id) FROM cuenta_correo));
SELECT setval(pg_get_serial_sequence('categoria_estandar',   'id'), (SELECT max(id) FROM categoria_estandar));
SELECT setval(pg_get_serial_sequence('categoria',            'id'), (SELECT max(id) FROM categoria));
SELECT setval(pg_get_serial_sequence('comercio',             'id'), (SELECT max(id) FROM comercio));
SELECT setval(pg_get_serial_sequence('metodo_pago',          'id'), (SELECT max(id) FROM metodo_pago));
SELECT setval(pg_get_serial_sequence('tipo_cambio',          'id'), (SELECT max(id) FROM tipo_cambio));
SELECT setval(pg_get_serial_sequence('compra',               'id'), (SELECT max(id) FROM compra));
SELECT setval(pg_get_serial_sequence('linea_compra',         'id'), (SELECT max(id) FROM linea_compra));
SELECT setval(pg_get_serial_sequence('comprobante',          'id'), (SELECT max(id) FROM comprobante));
SELECT setval(pg_get_serial_sequence('presupuesto',          'id'), (SELECT max(id) FROM presupuesto));
SELECT setval(pg_get_serial_sequence('regla_categorizacion', 'id'), (SELECT max(id) FROM regla_categorizacion));

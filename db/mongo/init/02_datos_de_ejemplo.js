// ============================================================================
//  Datos de ejemplo · MongoDB
//  Gastonomo · EIF509 · Laboratorio 2
//
//  Seis bitácoras que corresponden a compras REALES del seed de PostgreSQL
//  (db/postgres/seeds/afterMigrate__datos_de_ejemplo.sql). Los compra_id,
//  categoria_id, regla_id y presupuesto_id de estos documentos son los mismos
//  identificadores que allá: las dos bases cuentan la misma historia desde su
//  propio lado.
//
//  Se eligieron para cubrir todas las formas de evento que existen:
//
//    compra  1 · ingesta limpia, categorizada por regla
//    compra  2 · captura manual con corrección de un renglón
//    compra  3 · compra en dólares con conversión de moneda
//    compra  7 · ingesta que el titular partió en dos renglones y corrigió
//    compra  9 · compra anulada que devolvió su monto al presupuesto
//    compra 11 · ingesta que quedó en revisión por comercio sin clasificar
//
//  Los tipos BSON son explícitos (NumberLong, NumberInt, NumberDecimal) porque
//  el validador de 01_bitacora_compras.js los exige y porque mongosh, si no se
//  le dice, guarda todo número como double. Los montos van en NumberDecimal por
//  la misma razón que en PostgreSQL van en NUMERIC: con punto flotante los
//  céntimos no cuadran.
//
//  La carga es idempotente: replaceOne con upsert sobre compra_id. Correr el
//  script dos veces deja la colección igual.
// ============================================================================

/* global db, print, NumberLong, NumberInt, NumberDecimal, ISODate */

const bd = db.getSiblingDB('gastonomo');

const SERVICIO_INGESTA = { tipo: 'SERVICIO', nombre: 'servicio-de-ingesta' };
const MOTOR_DE_REGLAS = { tipo: 'SISTEMA', nombre: 'motor-de-reglas' };
const titular = (id) => ({ tipo: 'TITULAR', usuario_id: NumberLong(id) });

const bitacoras = [

  // --------------------------------------------------------------------------
  //  Compra 1 · Automercado, 45 320 colones, llegó por correo y la regla 1 la
  //  clasificó sola. Es el camino feliz completo.
  // --------------------------------------------------------------------------
  {
    compra_id: NumberLong(1),
    usuario_id: NumberLong(1),
    estado_actual: 'CONCILIADA',
    abierta_en: ISODate('2026-08-03T20:22:04Z'),
    actualizada_en: ISODate('2026-08-03T20:22:07Z'),
    eventos: [
      {
        secuencia: NumberInt(1),
        tipo: 'INGESTA_RECIBIDA',
        ocurrido_en: ISODate('2026-08-03T20:22:04Z'),
        actor: SERVICIO_INGESTA,
        datos: {
          comprobante_id: NumberLong(1),
          cuenta_correo_id: NumberLong(1),
          mensaje_id: 'BAC-2026-08-03-0001',
          remitente: 'notificaciones@baccredomatic.cr',
          asunto: 'Notificacion de compra',
        },
      },
      {
        secuencia: NumberInt(2),
        tipo: 'PARSEO_COMPROBANTE',
        ocurrido_en: ISODate('2026-08-03T20:22:05Z'),
        actor: SERVICIO_INGESTA,
        datos: {
          confianza: 1.0,
          patron_remitente: 'bac.notificacion-compra.v3',
          campos_extraidos: {
            monto: NumberDecimal('45320.00'),
            moneda: 'CRC',
            ultimos_cuatro: '8823',
            comercio_crudo: 'AUTOMERCADO #12 SAN PEDRO',
            fecha: '2026-08-03T14:22:00-06:00',
          },
          campos_faltantes: [],
          // El cuerpo del correo se descartó aquí mismo: de él solo queda el
          // mensaje_id del evento anterior.
          cuerpo_descartado: true,
        },
      },
      {
        secuencia: NumberInt(3),
        tipo: 'EMPAREJAMIENTO_METODO_PAGO',
        ocurrido_en: ISODate('2026-08-03T20:22:05Z'),
        actor: SERVICIO_INGESTA,
        datos: {
          ultimos_cuatro: '8823',
          resultado: 'EMPAREJADO',
          metodo_pago_id: NumberLong(2),
        },
      },
      {
        secuencia: NumberInt(4),
        tipo: 'RESOLUCION_COMERCIO',
        ocurrido_en: ISODate('2026-08-03T20:22:06Z'),
        actor: SERVICIO_INGESTA,
        datos: {
          nombre_crudo: 'AUTOMERCADO #12 SAN PEDRO',
          nombre_normalizado: 'AUTOMERCADO',
          estrategia: 'TRIGRAMAS',
          similitud: 0.62,
          comercio_id: NumberLong(1),
          comercio_creado: false,
        },
      },
      {
        secuencia: NumberInt(5),
        tipo: 'CATEGORIZACION_AUTOMATICA',
        ocurrido_en: ISODate('2026-08-03T20:22:06Z'),
        actor: MOTOR_DE_REGLAS,
        datos: {
          origen: 'REGLA',
          regla_id: NumberLong(1),
          campo: 'COMERCIO_NORMALIZADO',
          patron: 'AUTOMERCADO',
          reglas_evaluadas: NumberInt(2),
          linea_id: NumberLong(1),
          categoria_id: NumberLong(2),
        },
      },
      {
        secuencia: NumberInt(6),
        tipo: 'IMPACTO_PRESUPUESTO',
        ocurrido_en: ISODate('2026-08-03T20:22:07Z'),
        actor: SERVICIO_INGESTA,
        datos: {
          presupuesto_id: NumberLong(1),
          categoria_id: NumberLong(2),
          monto_aplicado: NumberDecimal('45320.00'),
          consumido_antes: NumberDecimal('0.00'),
          consumido_despues: NumberDecimal('45320.00'),
          porcentaje_despues: 37.77,
          umbral: NumberInt(80),
          alerta_disparada: false,
        },
      },
      {
        secuencia: NumberInt(7),
        tipo: 'CAMBIO_ESTADO',
        ocurrido_en: ISODate('2026-08-03T20:22:07Z'),
        actor: SERVICIO_INGESTA,
        datos: { de: 'BORRADOR', a: 'REGISTRADA' },
      },
      {
        secuencia: NumberInt(8),
        tipo: 'CAMBIO_ESTADO',
        ocurrido_en: ISODate('2026-08-03T20:22:07Z'),
        actor: SERVICIO_INGESTA,
        datos: { de: 'REGISTRADA', a: 'CONCILIADA', comprobante_id: NumberLong(1) },
      },
    ],
  },

  // --------------------------------------------------------------------------
  //  Compra 2 · Capturada a mano con tres renglones. El titular corrigió el
  //  detergente, que el comercio había mandado a Supermercado.
  // --------------------------------------------------------------------------
  {
    compra_id: NumberLong(2),
    usuario_id: NumberLong(1),
    estado_actual: 'REGISTRADA',
    abierta_en: ISODate('2026-08-07T23:40:00Z'),
    actualizada_en: ISODate('2026-08-07T23:46:12Z'),
    eventos: [
      {
        secuencia: NumberInt(1),
        tipo: 'DESGLOSE_MANUAL',
        ocurrido_en: ISODate('2026-08-07T23:43:00Z'),
        actor: titular(1),
        datos: {
          renglones: NumberInt(3),
          lineas: [
            { linea_id: NumberLong(2), descripcion: 'Arroz 1 kg', subtotal: NumberDecimal('2900.00') },
            { linea_id: NumberLong(3), descripcion: 'Leche 1 L', subtotal: NumberDecimal('2970.00'), exento_impuesto: true },
            { linea_id: NumberLong(4), descripcion: 'Detergente 3 kg', subtotal: NumberDecimal('4000.00'), descuento: NumberDecimal('250.00') },
          ],
          impuesto_calculado: NumberDecimal('897.00'),
          nota: 'La leche va exenta, por eso el impuesto no es el 13 % del subtotal completo',
        },
      },
      {
        secuencia: NumberInt(2),
        tipo: 'CATEGORIZACION_AUTOMATICA',
        ocurrido_en: ISODate('2026-08-07T23:43:01Z'),
        actor: MOTOR_DE_REGLAS,
        datos: {
          // Ninguna regla coincidió: se usó la categoría sugerida del comercio.
          origen: 'COMERCIO',
          comercio_id: NumberLong(4),
          categoria_estandar_id: NumberLong(2),
          categoria_id: NumberLong(2),
          reglas_evaluadas: NumberInt(5),
          lineas: [NumberLong(2), NumberLong(3), NumberLong(4)],
        },
      },
      {
        secuencia: NumberInt(3),
        tipo: 'CORRECCION_MANUAL',
        ocurrido_en: ISODate('2026-08-07T23:45:30Z'),
        actor: titular(1),
        datos: {
          linea_id: NumberLong(4),
          categoria_anterior_id: NumberLong(2),
          categoria_nueva_id: NumberLong(8),
          motivo_titular: 'El detergente es limpieza, no alimentacion',
          regla_ofrecida: true,
          regla_aceptada: false,
          por_que_no: 'Una regla por comercio mandaria TODO Mas x Menos a Hogar',
        },
      },
      {
        secuencia: NumberInt(4),
        tipo: 'IMPACTO_PRESUPUESTO',
        ocurrido_en: ISODate('2026-08-07T23:46:12Z'),
        actor: titular(1),
        datos: {
          presupuesto_id: NumberLong(1),
          categoria_id: NumberLong(2),
          monto_aplicado: NumberDecimal('5870.00'),
          consumido_antes: NumberDecimal('45320.00'),
          consumido_despues: NumberDecimal('51190.00'),
          porcentaje_despues: 42.66,
          umbral: NumberInt(80),
          alerta_disparada: false,
        },
      },
      {
        secuencia: NumberInt(5),
        tipo: 'IMPACTO_PRESUPUESTO',
        ocurrido_en: ISODate('2026-08-07T23:46:12Z'),
        actor: titular(1),
        datos: {
          presupuesto_id: NumberLong(2),
          categoria_id: NumberLong(8),
          monto_aplicado: NumberDecimal('4000.00'),
          consumido_antes: NumberDecimal('0.00'),
          consumido_despues: NumberDecimal('4000.00'),
          porcentaje_despues: 10.0,
          umbral: NumberInt(80),
          alerta_disparada: false,
        },
      },
      {
        secuencia: NumberInt(6),
        tipo: 'CAMBIO_ESTADO',
        ocurrido_en: ISODate('2026-08-07T23:46:12Z'),
        actor: titular(1),
        datos: { de: 'BORRADOR', a: 'REGISTRADA' },
      },
    ],
  },

  // --------------------------------------------------------------------------
  //  Compra 3 · Spotify en dólares. El evento de conversión es la trazabilidad
  //  de la tasa: guarda con qué número y de qué día se convirtió.
  // --------------------------------------------------------------------------
  {
    compra_id: NumberLong(3),
    usuario_id: NumberLong(1),
    estado_actual: 'CONCILIADA',
    abierta_en: ISODate('2026-08-05T08:11:02Z'),
    actualizada_en: ISODate('2026-08-05T08:11:05Z'),
    eventos: [
      {
        secuencia: NumberInt(1),
        tipo: 'INGESTA_RECIBIDA',
        ocurrido_en: ISODate('2026-08-05T08:11:02Z'),
        actor: SERVICIO_INGESTA,
        datos: {
          comprobante_id: NumberLong(2),
          cuenta_correo_id: NumberLong(1),
          mensaje_id: 'SPOT-2026-08-05-77120',
          remitente: 'no-reply@spotify.com',
          asunto: 'Tu recibo de Spotify',
        },
      },
      {
        secuencia: NumberInt(2),
        tipo: 'PARSEO_COMPROBANTE',
        ocurrido_en: ISODate('2026-08-05T08:11:03Z'),
        actor: SERVICIO_INGESTA,
        datos: {
          confianza: 0.95,
          patron_remitente: 'spotify.recibo.v1',
          campos_extraidos: {
            monto: NumberDecimal('11.99'),
            moneda: 'USD',
            ultimos_cuatro: '6411',
            comercio_crudo: 'SPOTIFY',
            fecha: '2026-08-05T02:11:00-06:00',
          },
          campos_faltantes: [],
          // Por debajo de 1.0 aunque no falte ningún campo: el remitente no es
          // un banco y su patrón es menos específico, así que la confianza se
          // pondera hacia abajo.
          nota: 'Patron de comercio, no de banco: se pondera al 0.95',
        },
      },
      {
        secuencia: NumberInt(3),
        tipo: 'EMPAREJAMIENTO_METODO_PAGO',
        ocurrido_en: ISODate('2026-08-05T08:11:03Z'),
        actor: SERVICIO_INGESTA,
        datos: { ultimos_cuatro: '6411', resultado: 'EMPAREJADO', metodo_pago_id: NumberLong(1) },
      },
      {
        secuencia: NumberInt(4),
        tipo: 'CONVERSION_MONEDA',
        ocurrido_en: ISODate('2026-08-05T08:11:04Z'),
        actor: SERVICIO_INGESTA,
        datos: {
          moneda_origen: 'USD',
          moneda_destino: 'CRC',
          monto_origen: NumberDecimal('11.99'),
          monto_destino: NumberDecimal('6144.64'),
          tasa: NumberDecimal('512.480000'),
          fecha_tasa: '2026-08-05',
          fuente: 'BCCR',
          // La tasa se copió a la compra en vez de referenciarse: corregir
          // después la fila del tipo de cambio no debe mover este total.
          tasa_congelada: true,
        },
      },
      {
        secuencia: NumberInt(5),
        tipo: 'CATEGORIZACION_AUTOMATICA',
        ocurrido_en: ISODate('2026-08-05T08:11:04Z'),
        actor: MOTOR_DE_REGLAS,
        datos: {
          origen: 'REGLA',
          regla_id: NumberLong(3),
          campo: 'COMERCIO_NORMALIZADO',
          patron: 'NETFLIX|SPOTIFY',
          reglas_evaluadas: NumberInt(3),
          linea_id: NumberLong(5),
          categoria_id: NumberLong(10),
        },
      },
      {
        secuencia: NumberInt(6),
        tipo: 'IMPACTO_PRESUPUESTO',
        ocurrido_en: ISODate('2026-08-05T08:11:05Z'),
        actor: SERVICIO_INGESTA,
        datos: {
          presupuesto_id: NumberLong(5),
          categoria_id: NumberLong(10),
          monto_aplicado: NumberDecimal('6144.64'),
          consumido_antes: NumberDecimal('0.00'),
          consumido_despues: NumberDecimal('6144.64'),
          porcentaje_despues: 51.21,
          umbral: NumberInt(90),
          alerta_disparada: false,
        },
      },
      {
        secuencia: NumberInt(7),
        tipo: 'CAMBIO_ESTADO',
        ocurrido_en: ISODate('2026-08-05T08:11:05Z'),
        actor: SERVICIO_INGESTA,
        datos: { de: 'BORRADOR', a: 'CONCILIADA', comprobante_id: NumberLong(2) },
      },
    ],
  },

  // --------------------------------------------------------------------------
  //  Compra 7 · El caso que mejor explica para qué existe esta colección: la
  //  ingesta creó una sola línea, el titular la partió en dos y corrigió la
  //  categoría de una de las mitades. Seis eventos de cuatro formas distintas.
  // --------------------------------------------------------------------------
  {
    compra_id: NumberLong(7),
    usuario_id: NumberLong(1),
    estado_actual: 'REGISTRADA',
    abierta_en: ISODate('2026-08-19T01:33:02Z'),
    actualizada_en: ISODate('2026-08-19T14:22:40Z'),
    eventos: [
      {
        secuencia: NumberInt(1),
        tipo: 'INGESTA_RECIBIDA',
        ocurrido_en: ISODate('2026-08-19T01:33:02Z'),
        actor: SERVICIO_INGESTA,
        datos: {
          comprobante_id: NumberLong(5),
          cuenta_correo_id: NumberLong(1),
          mensaje_id: 'BAC-2026-08-18-0517',
          remitente: 'notificaciones@baccredomatic.cr',
          asunto: 'Notificacion de compra',
        },
      },
      {
        secuencia: NumberInt(2),
        tipo: 'PARSEO_COMPROBANTE',
        ocurrido_en: ISODate('2026-08-19T01:33:03Z'),
        actor: SERVICIO_INGESTA,
        datos: {
          confianza: 1.0,
          patron_remitente: 'bac.notificacion-compra.v3',
          campos_extraidos: {
            monto: NumberDecimal('12400.00'),
            moneda: 'CRC',
            ultimos_cuatro: '6411',
            comercio_crudo: 'AUTOMERCADO #12 SAN PEDRO',
            fecha: '2026-08-18T19:33:00-06:00',
          },
          campos_faltantes: [],
          cuerpo_descartado: true,
        },
      },
      {
        secuencia: NumberInt(3),
        tipo: 'CATEGORIZACION_AUTOMATICA',
        ocurrido_en: ISODate('2026-08-19T01:33:04Z'),
        actor: MOTOR_DE_REGLAS,
        datos: {
          origen: 'REGLA',
          regla_id: NumberLong(1),
          campo: 'COMERCIO_NORMALIZADO',
          patron: 'AUTOMERCADO',
          reglas_evaluadas: NumberInt(2),
          linea_id: NumberLong(9),
          categoria_id: NumberLong(2),
        },
      },
      {
        secuencia: NumberInt(4),
        tipo: 'DESGLOSE_MANUAL',
        ocurrido_en: ISODate('2026-08-19T14:20:11Z'),
        actor: titular(1),
        datos: {
          // El refinamiento que describe el dominio: el cargo entró como un
          // solo renglón y el titular decidió partirlo.
          linea_origen_id: NumberLong(9),
          monto_origen: NumberDecimal('12400.00'),
          lineas_resultantes: [
            { linea_id: NumberLong(9), descripcion: 'Automercado - alimentos', subtotal: NumberDecimal('7440.00'), proporcion: 0.6 },
            { linea_id: NumberLong(10), descripcion: 'Automercado - limpieza', subtotal: NumberDecimal('4960.00'), proporcion: 0.4 },
          ],
        },
      },
      {
        secuencia: NumberInt(5),
        tipo: 'CORRECCION_MANUAL',
        ocurrido_en: ISODate('2026-08-19T14:21:02Z'),
        actor: titular(1),
        datos: {
          linea_id: NumberLong(10),
          categoria_anterior_id: NumberLong(2),
          categoria_nueva_id: NumberLong(8),
          motivo_titular: 'La mitad de limpieza va a Hogar',
          regla_ofrecida: true,
          regla_aceptada: false,
          por_que_no: 'Automercado seguira siendo Supermercado por defecto',
        },
      },
      {
        secuencia: NumberInt(6),
        tipo: 'IMPACTO_PRESUPUESTO',
        ocurrido_en: ISODate('2026-08-19T14:22:40Z'),
        actor: titular(1),
        datos: {
          presupuesto_id: NumberLong(1),
          categoria_id: NumberLong(2),
          monto_aplicado: NumberDecimal('7440.00'),
          consumido_antes: NumberDecimal('51190.00'),
          consumido_despues: NumberDecimal('58630.00'),
          porcentaje_despues: 48.86,
          umbral: NumberInt(80),
          alerta_disparada: false,
        },
      },
      {
        secuencia: NumberInt(7),
        tipo: 'IMPACTO_PRESUPUESTO',
        ocurrido_en: ISODate('2026-08-19T14:22:40Z'),
        actor: titular(1),
        datos: {
          presupuesto_id: NumberLong(2),
          categoria_id: NumberLong(8),
          monto_aplicado: NumberDecimal('4960.00'),
          consumido_antes: NumberDecimal('22750.00'),
          consumido_despues: NumberDecimal('27710.00'),
          porcentaje_despues: 69.28,
          umbral: NumberInt(80),
          alerta_disparada: false,
        },
      },
      {
        secuencia: NumberInt(8),
        tipo: 'CAMBIO_ESTADO',
        ocurrido_en: ISODate('2026-08-19T14:22:40Z'),
        actor: titular(1),
        datos: { de: 'BORRADOR', a: 'REGISTRADA' },
      },
    ],
  },

  // --------------------------------------------------------------------------
  //  Compra 9 · Anulada. La compra no se borra y el presupuesto recupera su
  //  monto: los dos hechos quedan escritos, que es lo que permite explicar
  //  después por qué Restaurantes aparece en cero habiendo tenido una compra.
  // --------------------------------------------------------------------------
  {
    compra_id: NumberLong(9),
    usuario_id: NumberLong(1),
    estado_actual: 'ANULADA',
    abierta_en: ISODate('2026-08-08T19:05:00Z'),
    actualizada_en: ISODate('2026-08-09T15:12:33Z'),
    eventos: [
      {
        secuencia: NumberInt(1),
        tipo: 'DESGLOSE_MANUAL',
        ocurrido_en: ISODate('2026-08-08T19:06:20Z'),
        actor: titular(1),
        datos: {
          renglones: NumberInt(1),
          lineas: [
            { linea_id: NumberLong(12), descripcion: 'Casado con pollo (2)', subtotal: NumberDecimal('3500.00') },
          ],
          impuesto_calculado: NumberDecimal('455.00'),
        },
      },
      {
        secuencia: NumberInt(2),
        tipo: 'CATEGORIZACION_AUTOMATICA',
        ocurrido_en: ISODate('2026-08-08T19:06:21Z'),
        actor: MOTOR_DE_REGLAS,
        datos: {
          origen: 'COMERCIO',
          comercio_id: NumberLong(7),
          categoria_estandar_id: NumberLong(3),
          categoria_id: NumberLong(3),
          reglas_evaluadas: NumberInt(5),
          linea_id: NumberLong(12),
        },
      },
      {
        secuencia: NumberInt(3),
        tipo: 'IMPACTO_PRESUPUESTO',
        ocurrido_en: ISODate('2026-08-08T19:06:22Z'),
        actor: titular(1),
        datos: {
          presupuesto_id: NumberLong(6),
          categoria_id: NumberLong(3),
          monto_aplicado: NumberDecimal('3955.00'),
          consumido_antes: NumberDecimal('0.00'),
          consumido_despues: NumberDecimal('3955.00'),
          porcentaje_despues: 7.91,
          umbral: NumberInt(80),
          alerta_disparada: false,
        },
      },
      {
        secuencia: NumberInt(4),
        tipo: 'CAMBIO_ESTADO',
        ocurrido_en: ISODate('2026-08-08T19:06:22Z'),
        actor: titular(1),
        datos: { de: 'BORRADOR', a: 'REGISTRADA' },
      },
      {
        secuencia: NumberInt(5),
        tipo: 'ANULACION',
        ocurrido_en: ISODate('2026-08-09T15:12:33Z'),
        actor: titular(1),
        datos: {
          motivo: 'COBRO_DUPLICADO',
          detalle: 'El comercio cobro dos veces el mismo almuerzo',
          presupuesto_id: NumberLong(6),
          devuelto_al_presupuesto: NumberDecimal('3955.00'),
          consumido_antes: NumberDecimal('3955.00'),
          consumido_despues: NumberDecimal('0.00'),
        },
      },
      {
        secuencia: NumberInt(6),
        tipo: 'CAMBIO_ESTADO',
        ocurrido_en: ISODate('2026-08-09T15:12:33Z'),
        actor: titular(1),
        datos: { de: 'REGISTRADA', a: 'ANULADA' },
      },
    ],
  },

  // --------------------------------------------------------------------------
  //  Compra 11 · La ingesta creó el comercio pero nadie lo ha clasificado, así
  //  que la compra se quedó en BORRADOR esperando al titular. Es el caso que
  //  explica por qué el renglón puede tener la categoría en NULL.
  // --------------------------------------------------------------------------
  {
    compra_id: NumberLong(11),
    usuario_id: NumberLong(2),
    estado_actual: 'BORRADOR',
    abierta_en: ISODate('2026-08-16T14:50:01Z'),
    actualizada_en: ISODate('2026-08-16T14:50:04Z'),
    eventos: [
      {
        secuencia: NumberInt(1),
        tipo: 'INGESTA_RECIBIDA',
        ocurrido_en: ISODate('2026-08-16T14:50:01Z'),
        actor: SERVICIO_INGESTA,
        datos: {
          comprobante_id: NumberLong(9),
          cuenta_correo_id: NumberLong(2),
          mensaje_id: 'SCOTIA-2026-08-16-4410',
          remitente: 'alertas@scotiabankcr.com',
          asunto: 'Consumo con su tarjeta',
        },
      },
      {
        secuencia: NumberInt(2),
        tipo: 'PARSEO_COMPROBANTE',
        ocurrido_en: ISODate('2026-08-16T14:50:02Z'),
        actor: SERVICIO_INGESTA,
        datos: {
          confianza: 0.75,
          patron_remitente: 'scotiabank.consumo.v1',
          campos_extraidos: {
            monto: NumberDecimal('42.17'),
            moneda: 'USD',
            ultimos_cuatro: '7730',
            comercio_crudo: 'AWS EMEA SARL',
            fecha: '2026-08-16T08:50:00-06:00',
          },
          campos_faltantes: [],
          nota: 'Justo en el umbral de 0.75: se procesa, pero se marca para revision',
        },
      },
      {
        secuencia: NumberInt(3),
        tipo: 'EMPAREJAMIENTO_METODO_PAGO',
        ocurrido_en: ISODate('2026-08-16T14:50:02Z'),
        actor: SERVICIO_INGESTA,
        datos: { ultimos_cuatro: '7730', resultado: 'EMPAREJADO', metodo_pago_id: NumberLong(6) },
      },
      {
        secuencia: NumberInt(4),
        tipo: 'RESOLUCION_COMERCIO',
        ocurrido_en: ISODate('2026-08-16T14:50:03Z'),
        actor: SERVICIO_INGESTA,
        datos: {
          nombre_crudo: 'AWS EMEA SARL',
          nombre_normalizado: 'AMAZON WEB SERVICES',
          estrategia: 'ALIAS_CONOCIDO',
          comercio_id: NumberLong(15),
          // El comercio se creó en el catálogo compartido, pero sin categoría
          // sugerida: nadie lo ha clasificado todavía.
          comercio_creado: true,
          categoria_estandar_sugerida_id: null,
        },
      },
      {
        secuencia: NumberInt(5),
        tipo: 'CONVERSION_MONEDA',
        ocurrido_en: ISODate('2026-08-16T14:50:03Z'),
        actor: SERVICIO_INGESTA,
        datos: {
          moneda_origen: 'USD',
          moneda_destino: 'CRC',
          monto_origen: NumberDecimal('42.17'),
          monto_destino: NumberDecimal('21641.64'),
          tasa: NumberDecimal('513.200000'),
          fecha_tasa: '2026-08-16',
          fuente: 'BCCR',
          tasa_congelada: true,
        },
      },
      {
        secuencia: NumberInt(6),
        tipo: 'REVISION_REQUERIDA',
        ocurrido_en: ISODate('2026-08-16T14:50:04Z'),
        actor: SERVICIO_INGESTA,
        datos: {
          motivo: 'COMERCIO_SIN_CATEGORIA',
          detalle: 'El comercio se creo pero no tiene categoria sugerida: la compra queda en BORRADOR hasta que el titular elija una',
          // Lo que hará el sistema cuando el titular la clasifique: guardar esa
          // categoría como sugerida del comercio, para que las siguientes
          // compras ahí entren solas.
          accion_al_resolver: 'GUARDAR_CATEGORIA_SUGERIDA_DEL_COMERCIO',
        },
      },
    ],
  },
];

let insertados = 0;
let actualizados = 0;

bitacoras.forEach((doc) => {
  const resultado = bd.bitacora_compras.replaceOne(
    { compra_id: doc.compra_id },
    doc,
    { upsert: true },
  );
  if (resultado.upsertedCount > 0) {
    insertados += 1;
  } else {
    actualizados += 1;
  }
});

print(
  'bitacora_compras: ' + insertados + ' documentos insertados, ' +
  actualizados + ' actualizados. Total en la coleccion: ' +
  bd.bitacora_compras.countDocuments(),
);

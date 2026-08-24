// ============================================================================
//  Colección bitacora_compras · MongoDB
//  Gastonomo · EIF509 · Laboratorio 2
//
//  QUÉ ES
//  ------
//  Un documento por compra, con la lista de eventos que explican cómo esa
//  compra llegó a ser lo que es: de qué correo nació, con cuánta confianza se
//  parseó, qué regla le puso la categoría, qué corrigió el titular, con qué
//  tasa se convirtió y a qué presupuesto impactó.
//
//  Es el subdominio que sostiene el diferenciador del sistema: de cualquier
//  total en pantalla se puede bajar hasta el comprobante que lo generó.
//
//  POR QUÉ VIVE AQUÍ Y NO EN POSTGRESQL
//  ------------------------------------
//  Las tres preguntas de diseño, respondidas en docs/modelo-de-datos.md y
//  resumidas aquí:
//
//    1 · ¿Cómo se lee el 90 % del tiempo? Completa y de una sola compra, cuando
//        el titular abre '¿por qué este gasto quedó en esta categoría?'. Nunca
//        se consultan eventos sueltos cruzando compras. → INCRUSTAR.
//
//    2 · ¿Cuánto crece en el peor caso? Acotado: una compra acumula entre 4 y
//        10 eventos, y una muy manoseada llegaría a 30. A ~400 bytes por
//        evento son 12 KB, contra el límite de 16 MB por documento. → INCRUSTAR.
//
//    3 · ¿Quién más lo necesita? Nadie. Solo su propia compra y su titular.
//        Ningún reporte agrega eventos entre compras. → INCRUSTAR.
//
//  Y la razón de forma: cada tipo de evento lleva campos DISTINTOS. Un parseo
//  guarda confianza y campos extraídos; una corrección manual guarda categoría
//  anterior y nueva; una conversión guarda tasa y fuente. En PostgreSQL esto
//  sería una tabla con quince columnas casi siempre nulas, o un EAV. Aquí cada
//  evento define su propia forma dentro de 'datos'.
//
//  QUÉ NO SE GUARDA
//  ----------------
//  Ninguna copia de los datos del núcleo. Los documentos referencian compras,
//  categorías y reglas por su id numérico de PostgreSQL: cada dato tiene un
//  dueño y el dueño de la compra es PostgreSQL. Las únicas cifras que sí viven
//  aquí son las que SON el evento (la tasa que se aplicó ese día, el consumo
//  del presupuesto antes y después): no son copias, son el hecho registrado.
//
//  Tampoco se guarda el cuerpo del correo. El sistema lee el mensaje, extrae
//  los cuatro campos que necesita y lo descarta; en la bitácora solo queda el
//  identificador del mensaje.
// ============================================================================

/* global db, print */

const bd = db.getSiblingDB('gastonomo');

const TIPOS_DE_EVENTO = [
  'INGESTA_RECIBIDA',            // llegó un correo nuevo de un buzón vinculado
  'PARSEO_COMPROBANTE',          // el parser extrajo los cuatro campos
  'EMPAREJAMIENTO_METODO_PAGO',  // se buscó la tarjeta por los últimos cuatro dígitos
  'RESOLUCION_COMERCIO',         // se resolvió el comercio por nombre normalizado
  'CATEGORIZACION_AUTOMATICA',   // una regla o el comercio pusieron la categoría
  'CORRECCION_MANUAL',           // el titular cambió la categoría
  'DESGLOSE_MANUAL',             // el titular partió el cargo en varios renglones
  'CONVERSION_MONEDA',           // se aplicó la tasa de la fecha de la compra
  'IMPACTO_PRESUPUESTO',         // se acumuló el consumo del mes
  'ALERTA_PRESUPUESTO',          // se cruzó el umbral configurado
  'CAMBIO_ESTADO',               // BORRADOR → REGISTRADA → CONCILIADA
  'REVISION_REQUERIDA',          // quedó pendiente de que el titular la mire
  'ANULACION',                   // se anuló y se devolvió el monto al presupuesto
];

// ----------------------------------------------------------------------------
//  Validador de esquema
//
//  «Elegir MongoDB porque es más fácil no diseñar el esquema» es el error que
//  produce un desorden de datos. La estructura se diseña igual; lo que cambia
//  es que aquí la define el patrón de consulta. Este validador fija lo que todo
//  evento debe traer —secuencia, tipo, cuándo y quién— y deja libre únicamente
//  el bloque 'datos', que es justamente lo que varía entre tipos de evento.
//
//  validationAction: 'error' rechaza la escritura, no solo la anota. Un
//  validador que solo avisa no es una restricción.
// ----------------------------------------------------------------------------
const validador = {
  $jsonSchema: {
    bsonType: 'object',
    title: 'Bitácora de trazabilidad de una compra',
    required: ['compra_id', 'usuario_id', 'estado_actual', 'abierta_en', 'actualizada_en', 'eventos'],
    additionalProperties: false,
    properties: {
      _id: { bsonType: 'objectId' },

      // Referencias al núcleo transaccional en PostgreSQL. Son long porque allá
      // las llaves primarias son BIGINT.
      compra_id: { bsonType: 'long', description: 'compra.id en PostgreSQL' },
      usuario_id: { bsonType: 'long', description: 'usuario.id en PostgreSQL' },

      // Se repite el estado de la compra para poder filtrar la bitácora sin ir
      // a PostgreSQL. Es el único dato replicado y se documenta como tal.
      estado_actual: {
        bsonType: 'string',
        enum: ['BORRADOR', 'REGISTRADA', 'CONCILIADA', 'ANULADA'],
      },

      abierta_en: { bsonType: 'date' },
      actualizada_en: { bsonType: 'date' },

      eventos: {
        bsonType: 'array',
        minItems: 1,
        // Tope defensivo, no un límite del negocio: si una bitácora llegara a
        // 200 eventos, la premisa «crece poco» dejó de ser cierta y hay que
        // revisar la decisión de incrustar en vez de descubrirlo por un
        // documento de 16 MB en producción.
        maxItems: 200,
        items: {
          bsonType: 'object',
          required: ['secuencia', 'tipo', 'ocurrido_en', 'actor'],
          additionalProperties: false,
          properties: {
            secuencia: { bsonType: 'int', minimum: 1 },
            tipo: { bsonType: 'string', enum: TIPOS_DE_EVENTO },
            ocurrido_en: { bsonType: 'date' },
            actor: {
              bsonType: 'object',
              required: ['tipo'],
              properties: {
                // TITULAR (una persona), SERVICIO (la ingesta) o SISTEMA (una
                // regla que se disparó sola).
                tipo: { bsonType: 'string', enum: ['TITULAR', 'SERVICIO', 'SISTEMA'] },
                usuario_id: { bsonType: ['long', 'null'] },
                nombre: { bsonType: ['string', 'null'] },
              },
            },
            // Sin 'properties': aquí es donde cada tipo de evento define su
            // propia forma. Es la razón de ser de esta colección.
            datos: { bsonType: 'object' },
          },
        },
      },
    },
  },
};

if (bd.getCollectionNames().indexOf('bitacora_compras') === -1) {
  bd.createCollection('bitacora_compras', {
    validator: validador,
    validationLevel: 'strict',
    validationAction: 'error',
  });
  print('bitacora_compras: colección creada con validador de esquema.');
} else {
  // Re-ejecutar el script actualiza el validador en vez de fallar.
  bd.runCommand({
    collMod: 'bitacora_compras',
    validator: validador,
    validationLevel: 'strict',
    validationAction: 'error',
  });
  print('bitacora_compras: validador actualizado.');
}

// ----------------------------------------------------------------------------
//  Índices
//
//  Mismo criterio que en PostgreSQL: uno por consulta real, no uno por campo.
// ----------------------------------------------------------------------------

// 1 · La consulta del 90 %: 'traeme la bitácora de esta compra'. Es único
//     porque una compra tiene UNA bitácora; dos documentos para la misma compra
//     significarían que parte de la historia quedó invisible.
bd.bitacora_compras.createIndex(
  { compra_id: 1 },
  { unique: true, name: 'uq_bitacora_compra' },
);

// 2 · 'Actividad reciente de este titular', para la pantalla de movimientos.
bd.bitacora_compras.createIndex(
  { usuario_id: 1, actualizada_en: -1 },
  { name: 'ix_bitacora_usuario_reciente' },
);

// 3 · Índice multiclave sobre el arreglo incrustado: responde '¿cuántas compras
//     tuvo que corregir a mano este titular?', que es la métrica con la que se
//     mide si la clasificación automática está mejorando. Sin él, medirlo
//     obligaría a recorrer la colección entera.
bd.bitacora_compras.createIndex(
  { usuario_id: 1, 'eventos.tipo': 1 },
  { name: 'ix_bitacora_usuario_tipo_evento' },
);

// 4 · Índice PARCIAL: 'qué compras aplicó esta regla'. Solo una minoría de los
//     eventos lleva regla_id, así que el índice guarda únicamente esos.
bd.bitacora_compras.createIndex(
  { 'eventos.datos.regla_id': 1 },
  {
    name: 'ix_bitacora_regla_aplicada',
    partialFilterExpression: { 'eventos.datos.regla_id': { $exists: true } },
  },
);

print('bitacora_compras: 4 índices asegurados.');

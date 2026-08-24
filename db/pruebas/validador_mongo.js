// ============================================================================
//  Comprobación del validador y de las consultas · MongoDB
//  Gastonomo · EIF509 · Laboratorio 2
//
//  Dos partes:
//    1. Seis intentos de escribir un documento que el validador debe rechazar.
//    2. Las consultas reales que justifican la forma de la colección, incluida
//       la medición del tamaño de los documentos (la pregunta 2 del método:
//       ¿cuánto crece en el peor caso?).
//
//  Cómo correrlo (con 'docker compose up -d' ya ejecutado):
//
//      docker compose exec -T mongo mongosh --quiet -u gastonomo -p gastonomo_local \
//          --authenticationDatabase admin gastonomo < db/pruebas/validador_mongo.js
//
//  No deja nada escrito: los seis documentos de prueba son inválidos y no
//  llegan a insertarse.
// ============================================================================

/* global db, print, NumberLong, NumberInt */

const bd = db.getSiblingDB('gastonomo');
const col = bd.bitacora_compras;

let rechazados = 0;
let aceptados = 0;

function esperaRechazo(nombre, doc) {
  try {
    col.insertOne(doc);
    aceptados += 1;
    print('FALLO LA PRUEBA -> ' + nombre + ' (el validador ACEPTO el documento invalido)');
    col.deleteOne({ compra_id: doc.compra_id });
  } catch (e) {
    rechazados += 1;
    print('RECHAZADO OK -> ' + nombre);
  }
}

const eventoValido = {
  secuencia: NumberInt(1),
  tipo: 'CAMBIO_ESTADO',
  ocurrido_en: new Date(),
  actor: { tipo: 'TITULAR' },
};

const base = (compraId) => ({
  compra_id: NumberLong(compraId),
  usuario_id: NumberLong(1),
  estado_actual: 'REGISTRADA',
  abierta_en: new Date(),
  actualizada_en: new Date(),
  eventos: [eventoValido],
});

print('--- 1 · El validador rechaza lo que el dominio no permite ---');

esperaRechazo('1. Tipo de evento que no existe en la lista cerrada',
  Object.assign(base(900), {
    eventos: [Object.assign({}, eventoValido, { tipo: 'ESTO_NO_EXISTE' })],
  }));

esperaRechazo('2. Evento sin actor (no se sabria quien lo provoco)',
  Object.assign(base(901), {
    eventos: [{ secuencia: NumberInt(1), tipo: 'CAMBIO_ESTADO', ocurrido_en: new Date() }],
  }));

esperaRechazo('3. Bitacora sin ningun evento',
  Object.assign(base(902), { eventos: [] }));

esperaRechazo('4. Campo de primer nivel no declarado (error de tipeo)',
  Object.assign(base(903), { campo_colado: 'ups' }));

esperaRechazo('5. Estado de compra que no existe en el dominio',
  Object.assign(base(904), { estado_actual: 'PAGADA' }));

esperaRechazo('6. Segunda bitacora para una compra que ya tiene una',
  base(1));

print('');
print('Resultado: ' + rechazados + ' de 6 documentos invalidos fueron rechazados.');
if (aceptados > 0) {
  print('ATENCION: el validador acepto ' + aceptados + ' documento(s) invalido(s).');
}

print('');
print('--- 2 · La consulta del 90 %: la bitacora completa de una compra ---');
const b7 = col.findOne({ compra_id: NumberLong(7) });
b7.eventos.forEach((e) => print('  ' + e.secuencia + '. ' + e.tipo + '  [' + e.actor.tipo + ']'));

const plan = col.find({ compra_id: NumberLong(7) }).explain().queryPlanner.winningPlan;
print('  etapa del plan: ' + (plan.inputStage ? plan.inputStage.stage : plan.stage) +
      '   (no debe decir COLLSCAN)');

print('');
print('--- 3 · Cuantas compras tuvo que corregir a mano el titular 1 ---');
print('  ' + col.countDocuments({ usuario_id: NumberLong(1), 'eventos.tipo': 'CORRECCION_MANUAL' }));

print('');
print('--- 4 · En que compras acerto cada regla de categorizacion ---');
col.aggregate([
  { $unwind: '$eventos' },
  { $match: { 'eventos.datos.regla_id': { $exists: true } } },
  { $group: { _id: '$eventos.datos.regla_id', compras: { $addToSet: '$compra_id' } } },
  { $sort: { _id: 1 } },
]).forEach((r) => print('  regla ' + r._id + ' -> compras ' + r.compras.join(', ')));

print('');
print('--- 5 · Cuanto pesa cada bitacora (la pregunta: cuanto crece) ---');
col.aggregate([
  { $project: { compra_id: 1, eventos: { $size: '$eventos' }, bytes: { $bsonSize: '$$ROOT' } } },
  { $sort: { compra_id: 1 } },
]).forEach((d) => print('  compra ' + d.compra_id + ': ' + d.eventos + ' eventos, ' + d.bytes + ' bytes'));
print('  (el limite de MongoDB por documento son 16 MB = 16 777 216 bytes)');

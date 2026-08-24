# ADR-002 · Subdominio documental en MongoDB: la trazabilidad de la compra

## Estado

**Aceptada** · Fecha: 23/08/2026 · Responsables: Jose Alexis Solís Carvajal y Luis Antonio Montes de Oca Ruiz

Revisa la conclusión de la sección *«Subdominio documental candidato»* de la
[Propuesta de Dominio](../propuesta-dominio.md) y la nota *«Una sola base de datos»* de
[Arquitectura](../arquitectura.md), ambas del Laboratorio 1.

## Contexto

El Laboratorio 2 pide construir la capa de datos completa con **persistencia políglota**: el núcleo
transaccional en PostgreSQL y **una** parte con forma documental en MongoDB, con la decisión de
incrustar o referenciar justificada por escrito.

En el Laboratorio 1 concluimos que nuestro dominio no tenía subdominio documental. El argumento era
que la parte que a primera vista lo parecía —los comprobantes que llegan por correo, con un formato
distinto por cada comercio— **no se almacena**: el sistema lee el mensaje, extrae los cuatro campos
que necesita (monto, últimos cuatro dígitos, comercio y fecha) y descarta el contenido. De ese correo
solo queda una fila en `comprobante` con datos perfectamente estructurados.

**Ese argumento sigue siendo válido y no lo revertimos**: guardar el cuerpo de los correos bancarios
de una persona significaría custodiar información financiera sensible que el sistema no necesita
para funcionar, y lo que no se almacena no se puede filtrar.

Lo que ese análisis no vio es que estábamos mirando el lugar equivocado. La parte documental del
sistema no son los datos que **entran**, sino el rastro de **lo que el sistema hizo con ellos**.

## Alternativas consideradas

| Candidato | Por qué se descartó |
|---|---|
| **Comprobantes crudos del correo** | No se almacenan, por privacidad y porque, extraídos los cuatro campos, el correo original no responde ninguna pregunta que el usuario vaya a hacer. Guardarlos solo para tener dónde usar MongoDB sería justificar la herramienta al revés. |
| **Catálogo de comercios con atributos variables** | Nuestros comercios tienen esquema fijo (nombre, normalizado, cédula, provincia) y, sobre todo, **los comparte todo el sistema**: un comercio aparece en miles de compras de titulares distintos. Tercera pregunta del método: si muchos lo comparten, es relacional. |
| **Presupuestos y su avance** | Participan en la transacción de conciliación y exigen que los números cuadren. Es exactamente la señal de alerta que el material del curso marca como error: si el dato participa en transacciones, va en PostgreSQL. |
| **Notificaciones enviadas al titular** | Encajaría (solo se agregan, estructura simple), pero es un subdominio pobre: sus documentos serían casi idénticos entre sí, así que no aprovecharía nada de lo que un modelo documental hace bien. Y todavía no existe en el alcance. |
| **Trazabilidad de la compra** ✅ | La elegida. Ver abajo. |

## Decisión

Implementamos en MongoDB la colección **`bitacora_compras`**: **un documento por compra**, con la
lista de eventos **incrustada**, que registra cómo esa compra llegó a ser lo que es.

No es un subdominio elegido para cumplir el requisito: es el **diferenciador declarado del sistema**.
La propuesta del Laboratorio 1 dice que de cualquier total en pantalla se puede bajar hasta el
comprobante que lo generó, pasando por el tipo de cambio y la regla de categorización que se
aplicaron. Eso es exactamente lo que guarda esta colección.

### Las tres preguntas de diseño

**1 · ¿Cómo se lee este dato el 90 % del tiempo?**
Siempre junto y completo, por unidad de compra. La consulta es una sola: el titular abre un gasto y
pregunta *«¿por qué esto quedó en esta categoría?»*. Se trae la bitácora entera y se pinta como una
línea de tiempo. Nunca se consultan eventos sueltos cruzando compras. → **incrustar**.

**2 · ¿Cuánto crece en el peor caso?**
Acotado. Una compra acumula entre 4 y 10 eventos; una muy manoseada —partida en renglones y
recategorizada varias veces— llegaría a 30. Medido sobre los datos de ejemplo: **entre 1 733 y 2 841
bytes con 6 a 8 eventos**, unos 350 bytes por evento. Aun con 200 eventos serían ~70 KB, el 0,4 % del
límite de 16 MB por documento. La lista no crece sin límite porque **está atada a un objeto que
termina**: una compra se concilia y deja de generar eventos. → **incrustar**.

**3 · ¿Quién más lo necesita?**
Nadie. Solo su propia compra y su titular. Ningún reporte del sistema agrega eventos entre compras:
los reportes suman montos, y los montos viven en PostgreSQL. → **incrustar**.

### La razón de forma

Además de las tres preguntas, hay una cuarta razón, y es la que hace que este subdominio sea
documental y no simplemente «una tabla más»: **cada tipo de evento lleva campos distintos**. Un
parseo guarda confianza y campos extraídos; una corrección manual guarda categoría anterior, nueva y
si se ofreció crear una regla; una conversión guarda tasa, fecha de la tasa y fuente; un impacto de
presupuesto guarda el consumo antes y después.

En PostgreSQL esto sería una tabla con quince columnas casi siempre nulas, o un EAV que hay que
reconstruir con pivotes en cada consulta. Ninguna de las dos es un buen modelo.

### Lo que queda en PostgreSQL, y por qué

Titulares, cuentas de correo, categorías, comercios, métodos de pago, compras, renglones,
comprobantes, presupuestos, reglas y tipos de cambio. Exigen integridad referencial entre doce
tablas, transacciones que escriben en cinco a la vez (el proceso de conciliación) y reglas de negocio
verificables en el propio esquema.

## Consecuencias

**A favor**

- La trazabilidad deja de ser una promesa del documento de diseño y pasa a ser un dato consultable.
- Los eventos nuevos no necesitan migración: un tipo de evento nuevo solo agrega su entrada a la
  lista cerrada del validador.
- El núcleo relacional no se ensucia con una tabla de auditoría de columnas nulas.
- La lectura del 90 % es **un solo acceso**: el documento entero por su índice único de `compra_id`.

**En contra, y asumido**

- **Dos bases que mantener**: dos contenedores, dos clientes, dos formas de respaldo. Lo acotamos a
  una sola colección precisamente para que el costo no crezca.
- **No hay integridad referencial entre las dos.** Si se borrara una compra de PostgreSQL, su
  bitácora quedaría huérfana. Lo mitiga el propio dominio: las compras **no se borran**, se anulan
  (`ON DELETE RESTRICT` en todo el esquema, y `ANULADA` como estado).
- **No hay transacción entre las dos bases.** Si la escritura en MongoDB fallara después de haber
  confirmado la compra en PostgreSQL, faltaría un evento en la bitácora. Es aceptable porque la
  bitácora **explica** lo que pasó, no lo decide: ningún saldo ni ningún total depende de ella. Si
  algún día dependiera, ese dato tendría que volver a PostgreSQL.
- **`estado_actual` está replicado** en el documento para poder filtrar bitácoras sin abrir una
  conexión a la otra base. Es el único dato duplicado y queda declarado como tal.

## Qué invalidaría esta decisión

- Si apareciera un reporte que **agregue eventos entre compras** de forma constante, estaríamos
  forzando *joins* entre colecciones y el subdominio habría dejado de ser documental.
- Si los eventos dejaran de estar atados a una compra que termina —por ejemplo, registrar también
  cada vez que alguien *mira* un gasto—, la lista crecería sin límite y habría que **referenciar** en
  vez de incrustar, con un documento por evento.
- Si estos datos participaran en una transacción con el núcleo, volverían a PostgreSQL.

El validador de la colección lleva `maxItems: 200` en el arreglo de eventos justamente como alarma de
la primera y la segunda: si una bitácora choca contra ese tope, la premisa dejó de ser cierta y hay
que revisar esta decisión.

## Referencias

- [Modelo de datos](../modelo-de-datos.md) — el modelo completo de las dos bases.
- [`db/mongo/init/01_bitacora_compras.js`](../../db/mongo/init/01_bitacora_compras.js) — colección,
  validador e índices.
- [ADR-003 · Flyway para las migraciones](ADR-003-flyway-para-las-migraciones.md)

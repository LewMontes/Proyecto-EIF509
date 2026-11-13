# ADR-004 · Dominio y alcance: control de gastos personales con ingesta desde el correo

## Estado y fecha

**Aceptada** · Fecha: 12/08/2026 · Responsables: Jose Alexis Solís Carvajal y Luis Antonio Montes de Oca Ruiz

Registrada en la Sesión 15 a partir de la [Propuesta de dominio](../propuesta-dominio.md) del
Laboratorio 1, que es donde se tomó la decisión.

## Contexto

El proyecto necesitaba un dominio con suficientes entidades y dos procesos de negocio —uno de ellos
transaccional— para sostener siete laboratorios incrementales, con dos integrantes y un ciclo.

El problema elegido: una persona en Costa Rica hace entre 60 y 120 compras al mes y no sabe en qué se
le va la plata, aunque toda la información exista repartida en tiquetes, correos del banco y SINPE.
Las apps internacionales no entienden colones, SINPE ni comercios locales, y las hojas de cálculo
caseras exigen digitar todo a mano y se abandonan.

Restricciones que pesaron:

- El alcance tenía que poder **terminarse** en el ciclo.
- Un comprobante bancario por correo trae **cuatro campos y nada más**: monto, últimos cuatro
  dígitos, comercio y fecha. Nunca el detalle de qué se compró.
- Son datos financieros de personas: lo que no se almacena no se puede filtrar.

## Decisión

Construimos **Gastonomo**, un sistema web **multiusuario** de control de gastos personales por
categoría que **observa, clasifica y explica** el gasto, pero nunca mueve dinero. Tiene dos procesos:
el **registro manual** de una compra con desglose (Proceso 1) y la **ingesta y conciliación
transaccional** de un comprobante de correo (Proceso 2).

Lo que queda **dentro**: cuentas aisladas por titular, buzones vinculados, compras con renglones,
categorías jerárquicas, comercios, métodos de pago, presupuestos mensuales, reglas de categorización
que aprenden de las correcciones, multimoneda con tipo de cambio histórico y dos roles (titular y
administrador).

Lo que queda **fuera**: pagos reales, conexión directa con bancos, presupuestos compartidos, archivo
de comprobantes, OCR de tiquetes, facturación ante Hacienda, contabilidad formal, app móvil nativa y
uso empresarial. La lista completa está en la [Propuesta § 5](../propuesta-dominio.md#5--alcance).

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| **Captura solo manual**, como una hoja de cálculo | Es exactamente lo que la gente abandona a las tres semanas. Sin ingesta automática el sistema no resuelve el problema; queda solo como Proceso 1, para lo que no llega por correo. |
| **Conexión directa con los bancos** (Open Banking o *scraping* de la banca en línea) | El *scraping* obliga a custodiar las credenciales bancarias del titular y se rompe con cada cambio del sitio. El correo ya llega solo y no exige credenciales del banco. |
| **Archivar los comprobantes** (guardar el correo completo) | Sería custodiar información financiera sensible que el sistema no necesita. Se extraen los cuatro campos y se descarta el cuerpo; lo que queda es la constancia del mensaje, que da la idempotencia. |
| **Presupuestos compartidos de un hogar** | Agrega una entidad Hogar, permisos entre personas y gasto consolidado. Con cuentas individuales, el aislamiento es una regla simple: toda consulta se filtra por titular. |
| **Clasificación automática pura**, sin intervención del titular | Cuando se equivoca, frustra y no hay forma de corregirla. Se eligió una clasificación híbrida: el sistema asigna y marca, y cada corrección puede crear una regla. |

## Consecuencias

**Lo que se gana**

- Un proceso transaccional real: la conciliación escribe en **cinco tablas** (`comprobante`,
  `compra`, `linea_compra`, `regla_categorizacion` y `presupuesto`), todo o nada.
- El titular es la raíz de aislamiento. Eso dio, de entrada, la regla que después sostuvo la
  seguridad: todo recurso se busca por id **y** por dueño ([ADR-006](ADR-006-autenticacion-jwt-stateless.md)).
- El diferenciador —bajar de cualquier total al comprobante, la tasa y la regla que lo produjeron—
  es lo que después justificó el subdominio documental ([ADR-002](ADR-002-subdominio-documental-en-mongodb.md)).

**Lo que se asume**

- **Cada banco es un lector nuevo.** Hoy existe solo el de BAC
  ([`comprobante_bac.py`](../../src/app/business/parsers/comprobante_bac.py)); un banco más es un
  formato de correo más que leer y probar.
- **El impuesto de lo ingerido no se desglosa.** El correo trae el total con IVA incluido; las compras
  que entran por ahí se guardan con `impuesto_desglosado = false` en vez de inventar un desglose.
- **El alcance es ambicioso para el ciclo.** A la fecha de este registro, el frontend React y el
  enlace OAuth2 del buzón siguen pendientes en este repositorio: el comprobante entra ya leído por
  `POST /api/v1/comprobantes` (ver [README § Estado del proyecto](../../README.md#estado-del-proyecto)).
- La conversión de moneda depende de que el BCCR (o Hacienda, de respaldo) responda: sin tasa para
  la fecha, el comprobante queda pendiente.

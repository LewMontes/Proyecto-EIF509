-- ============================================================================
--  V8 · Roles de la cuenta y buzones registrados sin tokens
--  Gastonomo · EIF509 · Laboratorio 5
--
--  El Laboratorio 5 expone la capa de negocio como una API protegida con JWT y
--  roles. Dos cosas de ese contrato le piden algo al esquema:
--
--    · usuario        → el rol de la cuenta, que es lo que la autorización por
--                       endpoint lee.
--    · cuenta_correo  → un buzón se puede registrar por la API antes de que
--                       exista el enlace OAuth2 con el proveedor.
--
--  Lo que NO cambia: ninguna columna existente cambia de tipo ni se borra, y
--  toda fila que ya existía sigue siendo válida.
-- ============================================================================


-- ----------------------------------------------------------------------------
--  1 · usuario · rol
--
--  Dos roles. TITULAR es cualquier persona que se registra y administra SUS
--  datos; ADMIN mantiene lo que es de todos (el catálogo compartido de
--  comercios y la lista de cuentas). Es un tipo cerrado y no un VARCHAR por lo
--  mismo que el resto de los enumerados del esquema: un rol mal escrito tiene
--  que fallar al guardarse, no al autorizar.
--
--  El DEFAULT es lo que deja a todas las cuentas que ya existían como TITULAR
--  -el privilegio mínimo- sin un UPDATE aparte.
-- ----------------------------------------------------------------------------
CREATE TYPE rol_usuario AS ENUM ('TITULAR', 'ADMIN');

ALTER TABLE usuario
    ADD COLUMN rol rol_usuario NOT NULL DEFAULT 'TITULAR';

COMMENT ON COLUMN usuario.rol IS
    'Qué puede hacer la cuenta. ADMIN mantiene el catálogo compartido; no gana acceso a los gastos de ningún titular.';


-- ----------------------------------------------------------------------------
--  2 · cuenta_correo · registrar el buzón antes de tener tokens
--
--  V1 exigía los dos tokens y su vencimiento porque el único camino para crear
--  un buzón era completar el OAuth2 con el proveedor. La API del Laboratorio 5
--  permite registrar el buzón primero -es a lo que se liga cada comprobante
--  que entra por POST /api/v1/comprobantes- y enlazarlo con el proveedor
--  después. Un buzón sin tokens es un buzón todavía no enlazado, no un error.
-- ----------------------------------------------------------------------------
ALTER TABLE cuenta_correo
    ALTER COLUMN token_acceso_cifrado   DROP NOT NULL,
    ALTER COLUMN token_refresco_cifrado DROP NOT NULL,
    ALTER COLUMN expira_en              DROP NOT NULL;

--  El mapeo conoce un cuarto estado del buzón -`ERROR`, cuando el proveedor
--  rechaza la sincronización por algo que no es un token vencido- que el tipo
--  de V1 no tenía.
ALTER TYPE estado_cuenta_correo ADD VALUE IF NOT EXISTS 'ERROR';


-- ----------------------------------------------------------------------------
--  3 · comprobante · la lista del titular
--
--  La consulta que lo justifica -`ComprobanteRepository.listar_de_usuario`, la
--  que alimenta GET /api/v1/comprobantes:
--
--      SELECT ... FROM comprobante
--       WHERE usuario_id = :u ORDER BY recibido_en DESC;
--
--  El UNIQUE de (cuenta_correo_id, mensaje_id) no la resuelve: no empieza por
--  el titular.
-- ----------------------------------------------------------------------------
CREATE INDEX ix_comprobante_usuario_recibido
    ON comprobante (usuario_id, recibido_en DESC);

-- ============================================================================
--  Comprobación de las restricciones · PostgreSQL
--  Gastonomo · EIF509 · Laboratorio 2
--
--  Doce intentos de meter un dato que el dominio prohíbe. Cada uno DEBE ser
--  rechazado por la base; si alguno pasara, la restricción que lo cubría no
--  está haciendo su trabajo.
--
--  Es la evidencia de la sección 6 de docs/modelo-de-datos.md: sirve para
--  demostrar que las reglas no viven solo en el servicio.
--
--  Cómo correrlo (con 'docker compose up -d' ya ejecutado):
--
--      docker compose exec -T postgres psql -U gastonomo -d gastonomo -q < db/pruebas/restricciones_postgres.sql
--
--  No modifica nada: cada intento falla, y el bloque atrapa el error y sigue.
-- ============================================================================

DO $$
DECLARE
    casos TEXT[][] := ARRAY[
        ['1. Total de compra que no cuadra con subtotal - descuento + impuesto',
         'INSERT INTO compra (usuario_id, comercio_id, fecha, moneda, subtotal, descuento, impuesto, total, tipo_cambio_aplicado, total_moneda_base) VALUES (1,1,''2026-08-22'',''CRC'',1000,0,130,9999,1,9999)'],

        ['2. Renglon clasificado en una categoria de OTRO titular',
         'INSERT INTO linea_compra (compra_id, usuario_id, categoria_id, descripcion, cantidad, precio_unitario, descuento, subtotal) VALUES (1,1,13,''Ajena'',1,100,0,100)'],

        ['3. El buzon reentrega un mensaje ya procesado (idempotencia)',
         'INSERT INTO comprobante (usuario_id, cuenta_correo_id, mensaje_id, remitente, recibido_en) VALUES (1,1,''BAC-2026-08-03-0001'',''x@y.cr'', now())'],

        ['4. Dos tarjetas del mismo titular terminadas en 6411',
         'INSERT INTO metodo_pago (usuario_id, alias, tipo, moneda, ultimos_cuatro) VALUES (1,''Otra'',''CREDITO'',''CRC'',''6411'')'],

        ['5. Dos reglas del mismo titular con la misma prioridad',
         'INSERT INTO regla_categorizacion (usuario_id, categoria_destino_id, nombre, campo, patron, prioridad) VALUES (1,2,''Dup'',''COMERCIO_NORMALIZADO'',''WALMART'',10)'],

        ['6. Efectivo con ultimos cuatro digitos',
         'INSERT INTO metodo_pago (usuario_id, alias, tipo, moneda, ultimos_cuatro) VALUES (1,''Efectivo2'',''EFECTIVO'',''CRC'',''1234'')'],

        ['7. Compra en colones con tipo de cambio distinto de 1',
         'INSERT INTO compra (usuario_id, comercio_id, fecha, moneda, subtotal, descuento, impuesto, total, tipo_cambio_aplicado, total_moneda_base) VALUES (1,1,''2026-08-22'',''CRC'',1000,0,0,1000,1.5,1500)'],

        ['8. Renglon cuyo subtotal no es cantidad x precio - descuento',
         'INSERT INTO linea_compra (compra_id, usuario_id, categoria_id, descripcion, cantidad, precio_unitario, descuento, subtotal) VALUES (1,1,2,''Mal'',2,100,0,999)'],

        ['9. Comercio con el nombre normalizado sin normalizar',
         'INSERT INTO comercio (nombre, nombre_normalizado) VALUES (''Prueba'', ''prueba'')'],

        ['10. Presupuesto del mes 13',
         'INSERT INTO presupuesto (usuario_id, categoria_id, anio, mes, monto_limite) VALUES (1,2,2026,13,1000)'],

        ['11. Comprobante FALLIDO sin motivo de fallo',
         'INSERT INTO comprobante (usuario_id, cuenta_correo_id, mensaje_id, remitente, recibido_en, estado, intentos_procesamiento) VALUES (1,1,''NUEVO-1'',''x@y.cr'', now(), ''FALLIDO'', 3)'],

        ['12. Titular con un correo que no tiene forma de correo',
         'INSERT INTO usuario (nombre_completo, correo, contrasena_hash) VALUES (''Prueba'', ''esto-no-es-correo'', ''$2b$12$aaaaaaaaaaaaaaaaaaaaaa'')']
    ];
    i          INT;
    rechazados INT := 0;
    aceptados  INT := 0;
BEGIN
    FOR i IN 1 .. array_length(casos, 1) LOOP
        BEGIN
            EXECUTE casos[i][2];
            aceptados := aceptados + 1;
            RAISE WARNING 'FALLO LA PRUEBA -> %  (la base ACEPTO el dato invalido)', casos[i][1];
        EXCEPTION WHEN others THEN
            rechazados := rechazados + 1;
            RAISE NOTICE 'RECHAZADO OK -> %  [%]', casos[i][1], left(SQLERRM, 70);
        END;
    END LOOP;

    RAISE NOTICE '';
    RAISE NOTICE 'Resultado: % de % intentos invalidos fueron rechazados por la base.',
                 rechazados, array_length(casos, 1);

    IF aceptados > 0 THEN
        RAISE EXCEPTION 'La base acepto % dato(s) que el dominio prohibe.', aceptados;
    END IF;
END $$;

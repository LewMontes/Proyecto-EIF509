# Hoja de evaluación del ensayo · Gastonomo

**Ensayo de la defensa · Sesión 15 · EIF509 · II Ciclo 2026**

| | |
|---|---|
| **Proyecto evaluado** | Gastonomo · control de gastos personales por categorías |
| **Integrantes** | Jose Alexis Solís Carvajal · Luis Antonio Montes de Oca Ruiz |
| **Evaluado por** | |

**Formato:** 10 minutos de presentación (demostración y arquitectura), seguidos de las preguntas.
Quien evalúa anota el puntaje que daría con la rúbrica del proyecto.

| Criterio | Qué observar | Máx. | Puntaje |
|---|---|:---:|:---:|
| Integración funcional | Los dos procesos funcionan de extremo a extremo en el sistema desplegado | 5 | |
| Calidad técnica global | Código ordenado, pruebas en verde y pipeline operativo | 4 | |
| Despliegue en la nube | Sistema estable y demostrable, con datos de demostración | 3 | |
| Documento de arquitectura | C4, cinco ADR, modelo de datos, seguridad y lecciones | 3 | |
| Defensa | Demostración fluida y dominio técnico de ambos integrantes | 5 | |
| | | **Total** | **/ 20** |

## Preguntas técnicas planteadas (al menos una a cada integrante)

Tomadas del banco de preguntas de la Sesión 15 y llevadas a este proyecto. La última columna dice qué
mostrar al responder.

| # | Pregunta | Dirigida a | Evidencia que se puede mostrar |
|---|---|---|---|
| 1 | *Transacciones.* ¿Qué ocurre si falla la actualización del presupuesto, el último paso de la conciliación? ¿Cómo lo comprueba una prueba? | | `test_un_fallo_al_acumular_el_presupuesto_no_deja_nada_escrito` en `tests/integracion/test_rollback_conciliacion.py` |
| 2 | *Seguridad.* ¿Cómo evitan que un titular consulte las compras de otro? ¿Dónde está el secreto JWT en producción? | | `obtener_de_usuario(id, usuario_id)`, `test_404_lo_de_otro_titular_es_indistinguible_de_lo_que_no_existe` y [ADR-006](adr/ADR-006-autenticacion-jwt-stateless.md) |
| 3 | *Concurrencia.* ¿Qué pasa si dos compras de la misma categoría y mes se confirman al mismo tiempo? | | Bloqueo optimista (`version`, migración `V9`), el `409` y `test_en_postgres_la_segunda_escritura_concurrente_es_rechazada` |

## Observaciones para mejorar antes del 5 de noviembre

1. **Sobre la demostración:**
2. **Sobre la explicación de la arquitectura:**
3. **Sobre las respuestas a las preguntas:**

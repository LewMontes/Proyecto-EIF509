# Muestras de comprobantes

Cada archivo de esta carpeta es un comprobante **anonimizado**: se conservan el formato,
las etiquetas y la puntuacion exactas del banco, pero el nombre del titular, el correo,
los ultimos cuatro digitos y los numeros de autorizacion y referencia estan cambiados.

Nunca subir a este repositorio un comprobante real sin anonimizar: el repositorio es
publico y esos campos identifican a una persona y a su tarjeta.

El signo `?` que aparece dentro de las palabras acentuadas no es un error de captura.
Es lo que devuelve la extraccion de texto cuando el comprobante viene de un correo
impreso a PDF desde el navegador: la fuente incrustada pierde el mapa de los acentos.
El parser tiene que tolerarlo, y por eso la muestra lo conserva tal cual.

## Comprobantes SINPE

`sinpe_bncr_dtr.txt` y `sinpe_bac_recibida.txt` son notificaciones de transferencia
SINPE recibida, una por banco -no de compra. Al contrario que las de BAC compra, estas
dos muestras se recibieron con los acentos intactos (una vino de un `.eml` crudo, la
otra de una exportacion a PDF que si conservo el mapa de acentos), asi que no llevan el
`?`. `transferencia_sinpe.py` igual tolera el comodin por si otra exportacion sí rompe
los acentos, como ya le pasa al comprobante de compra -no es una rareza confirmada en
estas dos muestras, es la misma precaucion aplicada por si acaso.

`sinpe_bac_recibida.txt` conserva un detalle real del formato: el campo de concepto
viene pegado a una fila de guiones bajos sin espacio (`Pago de prueba________.Día y
hora`) -es el relleno visual de una plantilla, no un error de esta muestra.

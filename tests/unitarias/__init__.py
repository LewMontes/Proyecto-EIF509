"""Pruebas unitarias con dobles: el servicio solo, sin base de datos.

El resto de `tests/` prueba los servicios contra SQLite en memoria -pruebas
*sociables*: el servicio corre con sus repositorios reales-. Las de este
paquete son *solitarias*: cada repositorio es un doble creado con
`unittest.mock.create_autospec`, así que lo único que se ejecuta de verdad es
el código del servicio.

`create_autospec` y no un `Mock()` pelado: el doble copia la firma de la clase
real, así que llamar a un método que no existe, o con los argumentos
equivocados, hace fallar la prueba en vez de pasar en silencio.
"""

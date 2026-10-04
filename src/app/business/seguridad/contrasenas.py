"""Hash y verificación de contraseñas de login.

Con bcrypt, no bruto (SHA-256 sobre la contraseña): un hash de propósito
general se calcula en microsegundos, así que probar millones de contraseñas
robadas de otra fuga contra estos hashes sería trivial. bcrypt es
deliberadamente lento -tiene un factor de costo incrustado en el propio
hash- y la sal va incluida en el resultado, así que no hay que guardarla
aparte ni gestionar ningún parámetro a mano.
"""

import bcrypt

# 12 es el valor por defecto de la librería y el mínimo recomendado hoy; cada
# +1 duplica el costo de calcular un hash (y de que alguien intente adivinar
# uno). Subirlo demasiado en un servidor sin GPU dedicada haría el login
# perceptiblemente lento para el titular real, no solo para quien ataque.
COSTO_POR_DEFECTO = 12

# bcrypt ignora en silencio todo lo que pase de 72 bytes: dos contraseñas
# largas que solo difieren después de ahí darían el mismo hash. Se corta acá,
# de forma explícita, y el DTO de entrada no deja pasar más que eso.
_BYTES_MAXIMOS = 72


def hashear_contrasena(contrasena: str, costo: int = COSTO_POR_DEFECTO) -> str:
    """Hashea una contraseña en claro para guardarla. Nunca se guarda la contraseña misma.

    `costo` existe para las pruebas, que crean decenas de cuentas y no ganan
    nada esperando un cuarto de segundo por cada una; la aplicación nunca lo
    pasa.
    """
    sal = bcrypt.gensalt(rounds=costo)
    return bcrypt.hashpw(_en_bytes(contrasena), sal).decode("ascii")


def verificar_contrasena(contrasena: str, hash_guardado: str) -> bool:
    """Compara una contraseña en claro contra el hash guardado, en tiempo constante.

    `bcrypt.checkpw` compara en tiempo constante a propósito: un `==` normal
    sobre los hashes se detiene en el primer byte distinto, y esa diferencia
    de tiempo -mínima, pero medible- es suficiente para que un atacante con
    muchos intentos reconstruya el hash byte a byte.
    """
    try:
        return bcrypt.checkpw(_en_bytes(contrasena), hash_guardado.encode("utf-8"))
    except ValueError:
        # `hash_guardado` no tiene la forma de un hash de bcrypt: no es una
        # contraseña que pueda «calzar».
        return False


def _en_bytes(contrasena: str) -> bytes:
    return contrasena.encode("utf-8")[:_BYTES_MAXIMOS]

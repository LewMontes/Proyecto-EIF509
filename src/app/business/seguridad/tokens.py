"""Emisión y lectura del JWT de acceso.

El token **es** la sesión: el servidor no guarda nada. Va firmado con HS256 y
una clave que solo conoce esta aplicación, así que cualquiera puede leerlo
pero nadie puede fabricar ni alterar uno sin que la firma deje de calzar. Por
eso adentro solo viaja lo mínimo para autorizar -quién es y qué rol tiene- y
nunca un dato sensible.

Las cuatro afirmaciones (*claims*) que lleva:

- `sub` · el id del titular. Es de donde sale el `usuario_id` de **toda**
  operación: ningún endpoint lo acepta del cuerpo ni de la URL.
- `rol` · para autorizar por endpoint.
- `iat` · cuándo se emitió.
- `exp` · cuándo vence. PyJWT lo verifica solo al decodificar.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.business.errors import NoAutenticado
from app.data.models.enums import RolUsuario

_ALGORITMO = "HS256"


@dataclass(frozen=True)
class TokenEmitido:
    """Un token recién firmado, con lo que el cliente necesita para usarlo."""

    access_token: str
    expira_en_segundos: int


@dataclass(frozen=True)
class ContenidoDelToken:
    """Lo que un token válido afirma sobre quien lo presenta."""

    usuario_id: int
    rol: RolUsuario


def emitir_token(usuario_id: int, rol: RolUsuario, secreto: str, minutos: int) -> TokenEmitido:
    """Firma un token de acceso para ese titular, válido por `minutos`."""
    ahora = datetime.now(UTC)
    contenido = {
        "sub": str(usuario_id),
        "rol": rol.value,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=minutos),
    }
    return TokenEmitido(
        access_token=jwt.encode(contenido, secreto, algorithm=_ALGORITMO),
        expira_en_segundos=minutos * 60,
    )


def leer_token(token: str, secreto: str) -> ContenidoDelToken:
    """Verifica la firma y el vencimiento, y devuelve lo que el token afirma.

    Cualquier cosa que no sea un token íntegro y vigente termina en
    `NoAutenticado`. `algorithms` se fija a propósito: sin esa lista, un token
    con `alg: none` -sin firma- pasaría la verificación.
    """
    try:
        contenido = jwt.decode(
            token, secreto, algorithms=[_ALGORITMO], options={"require": ["sub", "exp"]}
        )
        return ContenidoDelToken(usuario_id=int(contenido["sub"]), rol=RolUsuario(contenido["rol"]))
    except jwt.ExpiredSignatureError as error:
        raise NoAutenticado("El token venció: hay que iniciar sesión de nuevo.") from error
    except (jwt.InvalidTokenError, KeyError, ValueError) as error:
        raise NoAutenticado("El token no es válido.") from error

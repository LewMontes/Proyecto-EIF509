"""Límite de intentos fallidos de inicio de sesión (OWASP A07:2025).

Sin límite, `POST /api/v1/auth/login` deja probar contraseñas sin fin contra
una cuenta: bcrypt hace lento cada intento, pero no los cuenta. Esto los
cuenta.

La regla: **5 intentos fallidos en 15 minutos bloquean esa cuenta 15
minutos.** Mientras dure el bloqueo el login responde `429` con `Retry-After`,
aunque la contraseña sea la correcta -si la acertada destrabara, el bloqueo no
frenaría a nadie-. Un inicio de sesión exitoso borra el conteo.

Se cuenta por correo y no por IP: la IP la comparten una universidad entera o
una red móvil, y quien prueba contraseñas cambia de IP sin esfuerzo; lo que no
cambia es la cuenta que ataca. El costo -alguien puede bloquear a propósito la
cuenta de otro por 15 minutos- es temporal y queda registrado como evento de
seguridad.

Vive en memoria del proceso. Con una sola instancia, que es como se despliega
este proyecto, alcanza; con varias haría falta un almacén compartido (Redis).
Está declarado en AUDITORIA-SEGURIDAD.md.
"""

import math
import threading
import time
from collections.abc import Callable

from app.business.errors import DemasiadosIntentos

MAXIMO_DE_FALLOS = 5
VENTANA_EN_SEGUNDOS = 15 * 60


class LimitadorDeIntentos:
    """Cuenta los fallos por clave dentro de una ventana deslizante."""

    def __init__(
        self,
        maximo: int = MAXIMO_DE_FALLOS,
        ventana_en_segundos: int = VENTANA_EN_SEGUNDOS,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self._maximo = maximo
        self._ventana = ventana_en_segundos
        self._reloj = reloj
        self._fallos: dict[str, list[float]] = {}
        # uvicorn atiende las peticiones en un pool de hilos: dos logins de la
        # misma cuenta pueden contarse a la vez.
        self._candado = threading.Lock()

    def verificar(self, clave: str) -> None:
        """Lanza `DemasiadosIntentos` si la clave está bloqueada ahora mismo."""
        with self._candado:
            fallos = self._vigentes(clave)
            if len(fallos) < self._maximo:
                return
            espera = math.ceil(fallos[0] + self._ventana - self._reloj())
        raise DemasiadosIntentos(
            "Demasiados intentos fallidos de inicio de sesión para esta cuenta. "
            f"Probá de nuevo en {max(espera, 1)} segundos.",
            segundos_de_espera=max(espera, 1),
        )

    def registrar_fallo(self, clave: str) -> None:
        with self._candado:
            self._fallos[clave] = [*self._vigentes(clave), self._reloj()]

    def reiniciar(self, clave: str) -> None:
        with self._candado:
            self._fallos.pop(clave, None)

    def _vigentes(self, clave: str) -> list[float]:
        """Los fallos de la clave que siguen dentro de la ventana. Se llama con el candado.

        Una clave sin fallos vigentes se borra del diccionario: si no, probar
        miles de correos distintos lo haría crecer sin límite.
        """
        limite = self._reloj() - self._ventana
        vigentes = [momento for momento in self._fallos.get(clave, []) if momento > limite]
        if vigentes:
            self._fallos[clave] = vigentes
        else:
            self._fallos.pop(clave, None)
        return vigentes

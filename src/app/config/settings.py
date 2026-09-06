"""Valores que cambian entre maquinas.

Se leen del ambiente para que la misma imagen del codigo corra en la maquina de
cada integrante, en la integracion continua y manana en el servidor, sin editar
ningun archivo.
"""

import os
import warnings
from dataclasses import dataclass
from functools import lru_cache

from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Carga las variables de .env al ambiente del proceso, si el archivo existe.
# Busca hacia arriba desde el directorio de trabajo actual, así que corre
# igual desde la raíz del proyecto o desde src/. En CI no hay .env -el
# archivo está en .gitignore- así que esto no hace nada y las variables
# reales las pone el workflow.
load_dotenv()


@dataclass(frozen=True)
class Configuracion:
    """Configuracion de la aplicacion. Inmutable: se lee una vez al arrancar."""

    nombre_aplicacion: str
    version: str
    url_base_datos: str

    # OAuth2 de Microsoft identity platform (Outlook / Microsoft 365).
    # El segmento de tenant en la URL de autorización tiene que coincidir con
    # el "Supported account types" que se eligió al registrar la app en Azure:
    #   - "common"    → app multi-tenant + cuentas personales (lo que usamos:
    #                   la app puede estar registrada bajo el tenant de una
    #                   universidad u organización, y aun así dejar entrar
    #                   cuentas personales como sabejosoli27@hotmail.com).
    #   - "consumers" → app registrada como "Personal accounts only".
    #   - "organizations" → solo cuentas de una organización, sin personales.
    # Un desajuste entre esto y cómo se registró la app da AADSTS50194 o
    # AADSTS700016 al autorizar.
    microsoft_client_id: str
    microsoft_client_secret: str
    microsoft_tenant: str
    microsoft_redirect_uri: str

    # OAuth2 de Google (Gmail).
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str

    # Mismo cliente de Google, mismo Client ID/Secret -pero "iniciar sesión
    # con Google" pide un alcance mucho más chico (openid email profile, no
    # gmail.readonly) y el titular vuelve a una página distinta del
    # frontend, así que necesita su propio redirect_uri registrado aparte en
    # Google Cloud (Data Access → agregar otra "Authorized redirect URI" al
    # mismo cliente, no un cliente nuevo).
    google_login_redirect_uri: str

    # Clave simetrica con la que se cifran los tokens antes de guardarlos.
    clave_cifrado_tokens: str

    # Origenes desde los que el frontend puede llamar a esta API (CORS).
    origenes_permitidos: list[str]

    # Servicio Web de Indicadores Economicos del Banco Central de Costa Rica
    # (tipo de cambio). A diferencia de Outlook/Gmail no es OAuth2: hay que
    # suscribirse una sola vez en https://gee.bccr.fi.cr/Indicadores/Suscripciones/UI/Suscripcion
    # con un correo, confirmar la suscripcion desde ese correo, y guardar el
    # token que el BCCR genera. Sin estas dos variables, la conversion de
    # moneda simplemente no aparece -el resto de la aplicacion sigue
    # funcionando igual, como con Outlook/Gmail sin configurar.
    bccr_correo: str
    bccr_token: str

    # Usuario de prueba que `sembrar_usuario_de_demostracion()` crea en una
    # base recién creada -no una cuenta real. Vive acá y no como constante en
    # `database.py` para que la contraseña de verdad quede en `.env`
    # (gitignorado) y no en un archivo que se sube al repositorio; los
    # valores por defecto (`demo@gastonomo.cr`/`demo1234`) solo importan para
    # una base nueva sin `.env` -CI, un clon recién hecho- y no son secretos.
    demo_correo: str
    demo_contrasena: str

    # Mongo del subdominio documental (bitácora de trazabilidad de compras).
    # Con default, a diferencia de las credenciales de OAuth: el `mongo` de
    # `docker compose up -d` ya trae usuario/clave fijos para desarrollo, así
    # que casi nadie necesita tocar esto -ver ADR-002 y BitacoraComprasService.
    #
    # La base es "gastonomo_app", NO "gastonomo": esa última es la que
    # siembra `db/mongo/init/02_datos_de_ejemplo.js` para el Laboratorio 2,
    # con compras de ejemplo numeradas 1-11. La app en vivo también numera
    # sus propias compras empezando en 1 (autoincremental de PostgreSQL), así
    # que compartir la misma base mezclaría eventos reales con la bitácora
    # de ejemplo del mismo id -exactamente lo que pasó la primera vez que se
    # probó esto en vivo, y lo que obligó a este cambio. Una base de Mongo
    # nueva no necesita "crearse" aparte: existe la primera vez que algo
    # escribe en ella.
    mongo_url: str = "mongodb://gastonomo:gastonomo_local@localhost:27017"
    mongo_db: str = "gastonomo_app"


@lru_cache
def obtener_configuracion() -> Configuracion:
    """Arma la configuracion desde el ambiente, con valores por defecto de desarrollo.

    Por defecto la base es un archivo SQLite local, para que el proyecto corra
    sin instalar nada y para que la integracion continua -que no levanta
    Docker- siga arrancando la app tal cual. Con 'docker compose up -d
    postgres' corriendo, GASTONOMO_URL_BASE_DATOS en el .env apunta esta misma
    aplicacion a esa base en su lugar; ver la seccion de PostgreSQL del
    README. El esquema lo sigue creando `crear_tablas()` desde los modelos de
    SQLAlchemy -es un esquema propio de la aplicacion, no el que migran las
    migraciones de Flyway de docs/adr/ADR-003, que entregan el modelo de
    dominio original del Laboratorio 2 como un ejercicio aparte.

    Las credenciales de Outlook y Gmail no tienen un valor de desarrollo posible:
    cada integrante tiene que registrar su propia app en Azure y en Google Cloud
    y ponerlas en su `.env`. Sin ellas, todo el resto del sistema sigue
    funcionando; solo fallan los endpoints de vinculacion de correo.
    """
    return Configuracion(
        nombre_aplicacion=os.getenv("GASTONOMO_NOMBRE", "Gastonomo"),
        version=os.getenv("GASTONOMO_VERSION", "0.1.0"),
        url_base_datos=os.getenv("GASTONOMO_URL_BASE_DATOS", "sqlite:///./gastonomo.sqlite3"),
        microsoft_client_id=os.getenv("GASTONOMO_MICROSOFT_CLIENT_ID", ""),
        microsoft_client_secret=os.getenv("GASTONOMO_MICROSOFT_CLIENT_SECRET", ""),
        microsoft_tenant=os.getenv("GASTONOMO_MICROSOFT_TENANT", "common"),
        microsoft_redirect_uri=os.getenv(
            "GASTONOMO_MICROSOFT_REDIRECT_URI",
            "http://localhost:5173/vincular/outlook/callback",
        ),
        google_client_id=os.getenv("GASTONOMO_GOOGLE_CLIENT_ID", ""),
        google_client_secret=os.getenv("GASTONOMO_GOOGLE_CLIENT_SECRET", ""),
        google_redirect_uri=os.getenv(
            "GASTONOMO_GOOGLE_REDIRECT_URI",
            "http://localhost:5173/vincular/gmail/callback",
        ),
        google_login_redirect_uri=os.getenv(
            "GASTONOMO_GOOGLE_LOGIN_REDIRECT_URI",
            "http://localhost:5173/iniciar-sesion/google/callback",
        ),
        clave_cifrado_tokens=_obtener_clave_cifrado_tokens(),
        origenes_permitidos=_obtener_origenes_permitidos(),
        bccr_correo=os.getenv("GASTONOMO_BCCR_CORREO", ""),
        bccr_token=os.getenv("GASTONOMO_BCCR_TOKEN", ""),
        demo_correo=os.getenv("GASTONOMO_DEMO_CORREO", "demo@gastonomo.cr"),
        demo_contrasena=os.getenv("GASTONOMO_DEMO_CONTRASENA", "demo1234"),
        mongo_url=os.getenv(
            "GASTONOMO_MONGO_URL", "mongodb://gastonomo:gastonomo_local@localhost:27017"
        ),
        mongo_db=os.getenv("GASTONOMO_MONGO_DB", "gastonomo_app"),
    )


def _obtener_origenes_permitidos() -> list[str]:
    """Lee los orígenes permitidos para CORS, separados por coma.

    El redirect_uri de OAuth apunta al frontend a propósito (ver
    `microsoft_redirect_uri`): es el frontend el que recibe al titular de
    vuelta y llama a esta API por `fetch` para completar la vinculación. Sin
    CORS habilitado hacia ese origen, el navegador bloquearía esa llamada.
    """
    origenes = os.getenv("GASTONOMO_ORIGENES_PERMITIDOS", "http://localhost:5173")
    return [origen.strip() for origen in origenes.split(",") if origen.strip()]


def _obtener_clave_cifrado_tokens() -> str:
    """Lee la clave de cifrado del ambiente, o genera una efimera para desarrollo.

    Una clave generada al vuelo no sirve mas alla de un arranque: al reiniciar
    el proceso cambia, y los tokens que se cifraron con la anterior quedan
    indescifrables (las cuentas de correo tocaria vincularlas de nuevo). Por
    eso se avisa por warning en vez de fallar: es comodo para levantar el
    proyecto la primera vez, pero no es apto para nada que deba sobrevivir un
    reinicio.
    """
    clave = os.getenv("GASTONOMO_CLAVE_CIFRADO_TOKENS")
    if clave:
        return clave
    warnings.warn(
        "GASTONOMO_CLAVE_CIFRADO_TOKENS no esta definida: se genero una clave "
        "temporal valida solo para este arranque. Los tokens de correo cifrados "
        "ahora no se van a poder leer despues de reiniciar. Definila con: "
        'python -c "from cryptography.fernet import Fernet; '
        'print(Fernet.generate_key().decode())"',
        stacklevel=2,
    )
    return Fernet.generate_key().decode()

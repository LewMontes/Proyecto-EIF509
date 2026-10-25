# ============================================================================
#  Imagen de la API (FastAPI + uvicorn) · Gastonomo · EIF509
#
#  Es el artefacto que despliega el pipeline: el job "verificar" la construye
#  y la prueba arrancada, y el job "desplegar" le avisa a la plataforma que
#  construya esta misma receta desde master.
#
#  Build de un solo paso: no hay nada que compilar -psycopg, cryptography y
#  bcrypt traen wheels prearmados para linux/amd64 y linux/arm64-, así que no
#  hace falta un toolchain de C en la imagen.
# ============================================================================
FROM python:3.14-slim

# Sin .pyc en la imagen y la salida sin búfer: cada línea JSON del registro
# llega a la plataforma en el momento, no cuando se llena un búfer.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GASTONOMO_ENTORNO=produccion \
    # Detrás del proxy de la plataforma, la IP real del cliente viene en
    # X-Forwarded-For. uvicorn la usa (--proxy-headers) solo si confía en
    # quien la manda; en la plataforma todo el tráfico entra por su proxy.
    FORWARDED_ALLOW_IPS="*"

WORKDIR /app

# Copiar solo lo que pyproject.toml necesita para instalar (metadata +
# código) antes que el resto -así la capa con las dependencias ya instaladas
# se reutiliza entre builds mientras no cambien.
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# La app no corre como root (OWASP A02:2025): si alguien lograra ejecutar
# código a través de ella, no tendría el contenedor entero.
RUN useradd --create-home --uid 10001 gastonomo && chown -R gastonomo /app
USER gastonomo

EXPOSE 8000

# Sin curl en la imagen -slim no lo trae y no vale la pena instalarlo solo
# para esto-, así que el healthcheck usa la librería estándar de Python.
# Le pega a /actuator/health, que además de la app verifica la base.
HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=20s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8000\")}/actuator/health')" || exit 1

# La plataforma asigna el puerto en $PORT; en local, 8000.
CMD ["sh", "-c", "exec uvicorn app.main:app --app-dir src --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]

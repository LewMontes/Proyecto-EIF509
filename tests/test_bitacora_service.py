"""BitacoraComprasService, contra un doble de colección de Mongo -sin Mongo real."""

import pytest
from pymongo.errors import PyMongoError

from app.business.services.bitacora_service import Actor, BitacoraComprasService
from app.data.repositories.bitacora_repository import BitacoraRepository


class _ColeccionFalsa:
    """Un doble mínimo de `pymongo.collection.Collection`: solo lo que usa
    `BitacoraComprasService` -`update_one` con upsert, `find_one`- guardado en
    un diccionario en memoria, sin tocar la red."""

    def __init__(self) -> None:
        self.documentos: dict[int, dict] = {}

    def find_one(self, filtro: dict, proyeccion: dict | None = None) -> dict | None:
        documento = self.documentos.get(filtro["compra_id"])
        if documento is None:
            return None
        if proyeccion:
            return {campo: documento[campo] for campo in proyeccion if campo in documento}
        return documento

    def update_one(self, filtro: dict, actualizacion: dict, upsert: bool = False) -> None:
        compra_id = filtro["compra_id"]
        documento = self.documentos.get(compra_id)
        if documento is None:
            if not upsert:
                return
            documento = dict(actualizacion.get("$setOnInsert", {}))
            documento["eventos"] = []
            self.documentos[compra_id] = documento
        documento.update(actualizacion.get("$set", {}))
        if "$push" in actualizacion:
            documento["eventos"].append(actualizacion["$push"]["eventos"])


class _ColeccionQueFalla:
    """Simula que Mongo no responde -cualquier operación revienta."""

    def find_one(self, *args, **kwargs):
        raise PyMongoError("Mongo no responde")

    def update_one(self, *args, **kwargs):
        raise PyMongoError("Mongo no responde")


@pytest.fixture
def coleccion() -> _ColeccionFalsa:
    return _ColeccionFalsa()


@pytest.fixture
def servicio(coleccion: _ColeccionFalsa) -> BitacoraComprasService:
    return BitacoraComprasService(BitacoraRepository(coleccion))


def test_registrar_evento_crea_el_documento_la_primera_vez(
    servicio: BitacoraComprasService, coleccion: _ColeccionFalsa
) -> None:
    servicio.registrar_evento(
        compra_id=7,
        usuario_id=1,
        estado_actual="REGISTRADA",
        tipo="PARSEO_COMPROBANTE",
        datos={"confianza": 1.0},
        actor=Actor(tipo="SERVICIO", nombre="ingesta-correo"),
    )

    documento = coleccion.documentos[7]
    assert documento["compra_id"] == 7
    assert documento["usuario_id"] == 1
    assert documento["estado_actual"] == "REGISTRADA"
    assert len(documento["eventos"]) == 1
    assert documento["eventos"][0]["secuencia"] == 1
    assert documento["eventos"][0]["tipo"] == "PARSEO_COMPROBANTE"
    assert documento["eventos"][0]["actor"]["tipo"] == "SERVICIO"


def test_registrar_varios_eventos_incrementa_la_secuencia(
    servicio: BitacoraComprasService, coleccion: _ColeccionFalsa
) -> None:
    actor = Actor(tipo="SERVICIO", nombre="ingesta-correo")
    servicio.registrar_evento(7, 1, "REGISTRADA", "PARSEO_COMPROBANTE", {}, actor)
    servicio.registrar_evento(7, 1, "REGISTRADA", "RESOLUCION_COMERCIO", {}, actor)
    servicio.registrar_evento(7, 1, "REGISTRADA", "CATEGORIZACION_AUTOMATICA", {}, actor)

    eventos = coleccion.documentos[7]["eventos"]
    assert [e["secuencia"] for e in eventos] == [1, 2, 3]
    assert [e["tipo"] for e in eventos] == [
        "PARSEO_COMPROBANTE",
        "RESOLUCION_COMERCIO",
        "CATEGORIZACION_AUTOMATICA",
    ]


def test_rechaza_un_tipo_de_evento_que_no_existe(servicio: BitacoraComprasService) -> None:
    with pytest.raises(ValueError):
        servicio.registrar_evento(7, 1, "REGISTRADA", "ESTO_NO_EXISTE", {}, Actor(tipo="SERVICIO"))


def test_bitacora_de_devuelve_los_eventos_en_orden(
    servicio: BitacoraComprasService,
) -> None:
    actor = Actor(tipo="SERVICIO", nombre="ingesta-correo")
    servicio.registrar_evento(7, 1, "REGISTRADA", "PARSEO_COMPROBANTE", {"confianza": 1.0}, actor)
    servicio.registrar_evento(7, 1, "REGISTRADA", "RESOLUCION_COMERCIO", {"comercio_id": 3}, actor)

    eventos = servicio.bitacora_de(7)

    assert eventos is not None
    assert len(eventos) == 2
    assert eventos[0]["tipo"] == "PARSEO_COMPROBANTE"
    assert eventos[1]["datos"] == {"comercio_id": 3}


def test_bitacora_de_una_compra_sin_eventos_da_none(servicio: BitacoraComprasService) -> None:
    assert servicio.bitacora_de(999) is None


def test_sin_coleccion_no_escribe_ni_revienta() -> None:
    """Mongo no configurado en este ambiente -el servicio sigue existiendo y
    cualquier llamado es un no-op, no un error."""
    servicio = BitacoraComprasService(BitacoraRepository(None))

    servicio.registrar_evento(7, 1, "REGISTRADA", "PARSEO_COMPROBANTE", {}, Actor(tipo="SERVICIO"))

    assert servicio.bitacora_de(7) is None


def test_un_mongo_caido_no_revienta_al_registrar() -> None:
    servicio = BitacoraComprasService(BitacoraRepository(_ColeccionQueFalla()))

    # No debe lanzar -la bitácora explica, no decide (ver ADR-002).
    servicio.registrar_evento(7, 1, "REGISTRADA", "PARSEO_COMPROBANTE", {}, Actor(tipo="SERVICIO"))


def test_un_mongo_caido_no_revienta_al_leer() -> None:
    servicio = BitacoraComprasService(BitacoraRepository(_ColeccionQueFalla()))

    assert servicio.bitacora_de(7) is None

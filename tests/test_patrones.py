"""Los dos patrones del dominio, probados solos: sin base, sin servicios, sin HTTP.

- **Cadena de responsabilidad** · `categorizacion.py`: tres fuentes con la
  misma interfaz, recorridas en orden.
- **State** · `ciclo_comprobante.py`: cada estado del comprobante sabe qué
  transiciones admite.

Que se puedan probar así -con objetos en memoria y dobles de tres líneas- es
la mitad de la razón de haberlos extraído.
"""

import pytest

from app.business.errors import TransicionDeComprobanteInvalida
from app.business.services.categorizacion import (
    CadenaDeCategorizacion,
    CategoriaElegidaPorElTitular,
    CategoriaResuelta,
    ContextoDeCategorizacion,
    FuenteDeCategoria,
    OrigenDeCategoria,
    ReglasDelTitular,
    SugerenciaDelComercio,
)
from app.business.services.ciclo_comprobante import (
    MAXIMO_DE_INTENTOS,
    EnRevisionManual,
    Fallido,
    Parseado,
    Procesado,
    Recibido,
    estado_de,
)
from app.data.models.comprobante import Comprobante
from app.data.models.enums import EstadoComprobante
from app.data.models.regla_categorizacion import ReglaCategorizacion

# ============================================================================
#  Cadena de responsabilidad
# ============================================================================

CONTEXTO = ContextoDeCategorizacion(
    usuario_id=1, comercio_id=7, comercio_normalizado="WALMART EXPRESS HEREDIA"
)


def _regla(patron: str, categoria_id: int, prioridad: int) -> ReglaCategorizacion:
    return ReglaCategorizacion(
        usuario_id=1,
        categoria_destino_id=categoria_id,
        nombre=patron,
        patron=patron,
        prioridad=prioridad,
        activa=True,
        veces_aplicada=0,
    )


class _FuenteEspia:
    """Un eslabón de prueba: responde lo que se le diga y anota que lo consultaron."""

    def __init__(self, respuesta: CategoriaResuelta | None) -> None:
        self.respuesta = respuesta
        self.consultas = 0

    def resolver(self, contexto: ContextoDeCategorizacion) -> CategoriaResuelta | None:
        self.consultas += 1
        return self.respuesta


def test_los_tres_eslabones_cumplen_el_protocolo() -> None:
    """Tres implementaciones de la misma interfaz: es lo que las hace intercambiables."""
    fuentes: list[FuenteDeCategoria] = [
        CategoriaElegidaPorElTitular(),
        ReglasDelTitular(lambda _: []),
        SugerenciaDelComercio(lambda _u, _c: None),
    ]

    assert all(fuente.resolver(CONTEXTO) is None for fuente in fuentes)


def test_gana_el_primer_eslabon_que_resuelve_y_los_siguientes_ni_se_consultan() -> None:
    primero = _FuenteEspia(None)
    segundo = _FuenteEspia(CategoriaResuelta(20, OrigenDeCategoria.REGLA))
    tercero = _FuenteEspia(CategoriaResuelta(30, OrigenDeCategoria.COMERCIO))

    resuelta = CadenaDeCategorizacion([primero, segundo, tercero]).resolver(CONTEXTO)

    assert resuelta.categoria_id == 20
    assert (primero.consultas, segundo.consultas, tercero.consultas) == (1, 1, 0)


def test_si_ningun_eslabon_resuelve_la_cadena_devuelve_none() -> None:
    eslabones = [_FuenteEspia(None), _FuenteEspia(None)]

    assert CadenaDeCategorizacion(eslabones).resolver(CONTEXTO) is None
    assert [eslabon.consultas for eslabon in eslabones] == [1, 1]


def test_la_precedencia_la_da_el_orden_en_que_se_arma_la_cadena() -> None:
    """La misma pareja de eslabones, en el otro orden, decide otra cosa."""
    regla = _FuenteEspia(CategoriaResuelta(20, OrigenDeCategoria.REGLA))
    comercio = _FuenteEspia(CategoriaResuelta(30, OrigenDeCategoria.COMERCIO))

    assert CadenaDeCategorizacion([regla, comercio]).resolver(CONTEXTO).categoria_id == 20
    assert CadenaDeCategorizacion([comercio, regla]).resolver(CONTEXTO).categoria_id == 30


def test_la_eleccion_del_titular_gana_sobre_sus_propias_reglas() -> None:
    cadena = CadenaDeCategorizacion(
        [
            CategoriaElegidaPorElTitular(),
            ReglasDelTitular(lambda _: [_regla("WALMART", 20, 1)]),
        ]
    )
    contexto = ContextoDeCategorizacion(1, 7, "WALMART EXPRESS HEREDIA", categoria_elegida_id=99)

    resuelta = cadena.resolver(contexto)

    assert resuelta.categoria_id == 99
    assert resuelta.origen == OrigenDeCategoria.TITULAR
    assert resuelta.regla is None


def test_entre_las_reglas_gana_la_de_menor_prioridad_y_se_devuelve_cual_acerto() -> None:
    excepcion = _regla("WALMART EXPRESS", 21, 1)
    general = _regla("WALMART", 20, 2)

    resuelta = ReglasDelTitular(lambda _: [excepcion, general]).resolver(CONTEXTO)

    assert resuelta.categoria_id == 21
    assert resuelta.origen == OrigenDeCategoria.REGLA
    assert resuelta.regla is excepcion, "quien llama le sube el contador a esta"


def test_las_reglas_se_leen_una_sola_vez_por_titular() -> None:
    lecturas: list[int] = []

    def reglas_de(usuario_id: int) -> list[ReglaCategorizacion]:
        lecturas.append(usuario_id)
        return [_regla("WALMART", 20, 1)]

    eslabon = ReglasDelTitular(reglas_de)
    for _ in range(5):
        eslabon.resolver(CONTEXTO)

    assert lecturas == [1], "cinco renglones de la misma compra, una sola consulta"


def test_sin_regla_que_coincida_decide_la_sugerencia_del_comercio() -> None:
    cadena = CadenaDeCategorizacion(
        [
            ReglasDelTitular(lambda _: [_regla("FARMACIA", 40, 1)]),
            SugerenciaDelComercio(lambda usuario_id, comercio_id: 30 if comercio_id == 7 else None),
        ]
    )

    resuelta = cadena.resolver(CONTEXTO)

    assert resuelta.categoria_id == 30
    assert resuelta.origen == OrigenDeCategoria.COMERCIO


# ============================================================================
#  State
# ============================================================================


def _comprobante(estado: EstadoComprobante = EstadoComprobante.RECIBIDO) -> Comprobante:
    return Comprobante(
        usuario_id=1,
        cuenta_correo_id=1,
        mensaje_id="m-1",
        remitente="banco@bac.cr",
        banco="BAC",
        confianza=0.0,
        estado=estado,
        intentos_procesamiento=0,
    )


@pytest.mark.parametrize(
    "estado, clase",
    [
        (EstadoComprobante.RECIBIDO, Recibido),
        (EstadoComprobante.PARSEADO, Parseado),
        (EstadoComprobante.REVISION_MANUAL, EnRevisionManual),
        (EstadoComprobante.PROCESADO, Procesado),
        (EstadoComprobante.FALLIDO, Fallido),
    ],
)
def test_cada_estado_guardado_tiene_su_clase(estado: EstadoComprobante, clase: type) -> None:
    assert isinstance(estado_de(_comprobante(estado)), clase)


def test_recibido_con_buena_confianza_pasa_a_parseado() -> None:
    comprobante = _comprobante()

    estado_de(comprobante).parsear(confianza=1.0, es_conciliable=True)

    assert comprobante.estado == EstadoComprobante.PARSEADO
    assert comprobante.confianza == 1.0
    assert comprobante.motivo_fallo is None


@pytest.mark.parametrize("confianza", [0.0, 0.5, 0.74])
def test_por_debajo_de_075_va_a_revision_manual(confianza: float) -> None:
    comprobante = _comprobante()

    estado_de(comprobante).parsear(confianza=confianza, es_conciliable=True)

    assert comprobante.estado == EstadoComprobante.REVISION_MANUAL
    assert "0.75" in comprobante.motivo_fallo


def test_exactamente_075_si_alcanza() -> None:
    comprobante = _comprobante()

    estado_de(comprobante).parsear(confianza=0.75, es_conciliable=True)

    assert comprobante.estado == EstadoComprobante.PARSEADO


def test_si_no_es_conciliable_va_a_revision_aunque_la_confianza_alcance() -> None:
    comprobante = _comprobante()

    estado_de(comprobante).parsear(1.0, es_conciliable=False, motivo="No es una compra.")

    assert comprobante.estado == EstadoComprobante.REVISION_MANUAL
    assert comprobante.motivo_fallo == "No es una compra."


def test_parseado_se_procesa_y_queda_ligado_a_su_compra() -> None:
    comprobante = _comprobante(EstadoComprobante.PARSEADO)
    comprobante.motivo_fallo = "Estaba esperando la tasa."

    estado_de(comprobante).procesar(compra_id=42)

    assert comprobante.estado == EstadoComprobante.PROCESADO
    assert comprobante.compra_id == 42
    assert comprobante.motivo_fallo is None


def test_dejar_pendiente_no_cambia_el_estado_ni_cuenta_un_intento() -> None:
    comprobante = _comprobante(EstadoComprobante.PARSEADO)

    estado_de(comprobante).dejar_pendiente("Sin tipo de cambio.")

    assert comprobante.estado == EstadoComprobante.PARSEADO
    assert comprobante.intentos_procesamiento == 0
    assert comprobante.motivo_fallo == "Sin tipo de cambio."


def test_al_tercer_fallo_pasa_a_fallido() -> None:
    comprobante = _comprobante(EstadoComprobante.PARSEADO)

    for intento in range(1, MAXIMO_DE_INTENTOS):
        estado_de(comprobante).registrar_fallo("se cayó")
        assert comprobante.estado == EstadoComprobante.PARSEADO, f"intento {intento}: sigue vivo"
    estado_de(comprobante).registrar_fallo("se cayó otra vez")

    assert comprobante.estado == EstadoComprobante.FALLIDO
    assert comprobante.intentos_procesamiento == MAXIMO_DE_INTENTOS == 3
    assert comprobante.motivo_fallo == "se cayó otra vez"


@pytest.mark.parametrize(
    "estado",
    [
        EstadoComprobante.RECIBIDO,
        EstadoComprobante.REVISION_MANUAL,
        EstadoComprobante.PROCESADO,
        EstadoComprobante.FALLIDO,
    ],
)
def test_solo_parseado_admite_conciliacion(estado: EstadoComprobante) -> None:
    comprobante = _comprobante(estado)

    assert estado_de(comprobante).admite_conciliacion is False
    with pytest.raises(TransicionDeComprobanteInvalida, match=estado.value):
        estado_de(comprobante).asegurar_conciliable()
    with pytest.raises(TransicionDeComprobanteInvalida):
        estado_de(comprobante).procesar(compra_id=1)

    assert estado_de(_comprobante(EstadoComprobante.PARSEADO)).admite_conciliacion is True


@pytest.mark.parametrize("estado", [EstadoComprobante.PROCESADO, EstadoComprobante.FALLIDO])
def test_los_estados_terminales_no_admiten_ninguna_transicion(estado: EstadoComprobante) -> None:
    ciclo = estado_de(_comprobante(estado))

    for operacion in (
        lambda: ciclo.parsear(1.0, True),
        lambda: ciclo.procesar(1),
        lambda: ciclo.dejar_pendiente("x"),
        lambda: ciclo.registrar_fallo("x"),
    ):
        with pytest.raises(TransicionDeComprobanteInvalida):
            operacion()
    assert ciclo.comprobante.estado == estado, "y el comprobante quedó como estaba"


def test_un_comprobante_ya_parseado_no_se_parsea_de_nuevo() -> None:
    with pytest.raises(TransicionDeComprobanteInvalida):
        estado_de(_comprobante(EstadoComprobante.PARSEADO)).parsear(1.0, True)

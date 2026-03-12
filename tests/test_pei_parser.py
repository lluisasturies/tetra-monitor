import os
import sys
import pytest
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.modules.setdefault("serial", mock.MagicMock())

from pei.hardware.pei_motorola import MotorolaPEI  # noqa: E402


@pytest.fixture
def pei():
    """Instancia de MotorolaPEI con el puerto serie completamente mockeado."""
    with mock.patch("pei.hardware.pei_motorola.serial.Serial") as mock_serial:
        instance = mock_serial.return_value
        instance.readline.return_value = b""
        p = MotorolaPEI(port="/dev/ttyUSB0", baud=9600)
        p.ser = instance
        yield p


# ---------------------------------------------------------------------------
# +CTXG — Transmission Grant
# ---------------------------------------------------------------------------

def test_ctxg_ptt_start(pei):
    event = pei._parse_event("+CTXG: 1,1,0")
    assert event is not None
    assert event.type == "PTT_START"


def test_ctxg_ptt_end(pei):
    event = pei._parse_event("+CTXG: 0,0,0")
    assert event is not None
    assert event.type == "PTT_END"


def test_ctxg_malformado_devuelve_none(pei):
    event = pei._parse_event("+CTXG: abc")
    assert event is None


# ---------------------------------------------------------------------------
# +CDTXC — Down Transmission Ceased
# ---------------------------------------------------------------------------

def test_cdtxc_ptt_end(pei):
    event = pei._parse_event("+CDTXC: 1")
    assert event is not None
    assert event.type == "PTT_END"


# ---------------------------------------------------------------------------
# +CTICN — Incoming Call Notification
# ---------------------------------------------------------------------------

def test_cticn_call_start_con_gssi_y_ssi(pei):
    event = pei._parse_event("+CTICN: 1,0,0,36001,0,,12345")
    assert event is not None
    assert event.type == "CALL_START"
    assert event.grupo == 36001
    assert event.ssi == 12345


def test_cticn_sin_ssi_suficientes_campos(pei):
    event = pei._parse_event("+CTICN: 1,0,0,36002")
    assert event is not None
    assert event.type == "CALL_START"
    assert event.grupo == 36002
    assert event.ssi == 0


def test_cticn_pocos_campos_usa_fallback(pei):
    # Con menos de 4 campos el parser usa grupo=0, ssi=0 como fallback seguro
    event = pei._parse_event("+CTICN: abc,xyz")
    assert event is not None
    assert event.type == "CALL_START"
    assert event.grupo == 0
    assert event.ssi == 0


def test_cticn_gssi_no_entero_devuelve_none(pei):
    # Con >=4 campos pero el 4º no es entero, sí lanza ValueError → None
    event = pei._parse_event("+CTICN: 1,0,0,GRUPO_MALO")
    assert event is None


# ---------------------------------------------------------------------------
# +CTCC — Call Connect
# ---------------------------------------------------------------------------

def test_ctcc_call_connected(pei):
    event = pei._parse_event("+CTCC: 1,0")
    assert event is not None
    assert event.type == "CALL_CONNECTED"


# ---------------------------------------------------------------------------
# +CTCR — Call Release
# ---------------------------------------------------------------------------

def test_ctcr_call_end(pei):
    event = pei._parse_event("+CTCR: 1,0")
    assert event is not None
    assert event.type == "CALL_END"


# ---------------------------------------------------------------------------
# +CTXD — Transmit Demand
# ---------------------------------------------------------------------------

def test_ctxd_tx_demand(pei):
    event = pei._parse_event("+CTXD: 1,0")
    assert event is not None
    assert event.type == "TX_DEMAND"


# ---------------------------------------------------------------------------
# Líneas desconocidas / vacías
# ---------------------------------------------------------------------------

def test_linea_desconocida_devuelve_none(pei):
    assert pei._parse_event("OK") is None
    assert pei._parse_event("") is None
    assert pei._parse_event("AT") is None
    assert pei._parse_event("ERROR") is None


# ---------------------------------------------------------------------------
# Validación de comandos AT
# ---------------------------------------------------------------------------

def test_set_active_gssi_formato_valido(pei):
    pei.send = mock.MagicMock(return_value="OK")
    pei.set_active_gssi("36001")
    pei.send.assert_called_once_with("AT+CTGS=36001")


def test_set_active_gssi_formato_invalido(pei):
    pei.send = mock.MagicMock()
    pei.set_active_gssi("GSSI_MALO!")
    pei.send.assert_not_called()


def test_set_active_gssi_demasiado_largo(pei):
    pei.send = mock.MagicMock()
    pei.set_active_gssi("123456789")  # 9 dígitos — excede máx 8
    pei.send.assert_not_called()


def test_set_scan_list_formato_valido(pei):
    pei.send = mock.MagicMock(return_value="OK")
    pei.set_scan_list("ListaScan1")
    # AT+CTSL: comando ETSI EN 300 392-5 para activar una scan list por nombre
    pei.send.assert_called_once_with("AT+CTSL=ListaScan1")


def test_set_scan_list_formato_invalido(pei):
    pei.send = mock.MagicMock()
    pei.set_scan_list("lista con espacios!")
    pei.send.assert_not_called()

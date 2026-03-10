import os
import sys
import pytest
import yaml
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.afiliacion import AfiliacionConfig


@pytest.fixture
def afiliacion_file(tmp_path):
    path = tmp_path / "afiliacion.yaml"
    path.write_text(yaml.dump({"afiliacion": {"gssi": "36001", "scan_list": "ListaScan1"}}))
    return path


def test_carga_inicial(afiliacion_file):
    af = AfiliacionConfig(afiliacion_file)
    assert af.gssi == "36001"
    assert af.scan_list == "ListaScan1"


def test_fichero_no_existe(tmp_path):
    """Sin fichero no debe lanzar excepción — usa valores vacíos."""
    af = AfiliacionConfig(tmp_path / "no_existe.yaml")
    assert af.gssi == ""
    assert af.scan_list is None


def test_scan_list_none_en_yaml(tmp_path):
    path = tmp_path / "afiliacion.yaml"
    path.write_text(yaml.dump({"afiliacion": {"gssi": "36001", "scan_list": None}}))
    af = AfiliacionConfig(path)
    assert af.scan_list is None


def test_update_gssi_valido(afiliacion_file):
    af = AfiliacionConfig(afiliacion_file)
    af.update_gssi("36002")
    assert af.gssi == "36002"
    with open(afiliacion_file) as f:
        data = yaml.safe_load(f)
    assert data["afiliacion"]["gssi"] == "36002"


def test_update_gssi_invalido_lanza_valueerror(afiliacion_file):
    af = AfiliacionConfig(afiliacion_file)
    with pytest.raises(ValueError):
        af.update_gssi("GSSI_MALO")


def test_update_gssi_demasiado_largo(afiliacion_file):
    af = AfiliacionConfig(afiliacion_file)
    with pytest.raises(ValueError):
        af.update_gssi("123456789")  # 9 dígitos


def test_update_scan_list_valida(afiliacion_file):
    af = AfiliacionConfig(afiliacion_file)
    af.update_scan_list("NuevaLista")
    assert af.scan_list == "NuevaLista"
    with open(afiliacion_file) as f:
        data = yaml.safe_load(f)
    assert data["afiliacion"]["scan_list"] == "NuevaLista"


def test_update_scan_list_invalida(afiliacion_file):
    af = AfiliacionConfig(afiliacion_file)
    with pytest.raises(ValueError):
        af.update_scan_list("lista con espacios!")


def test_update_scan_list_none_desactiva(afiliacion_file):
    af = AfiliacionConfig(afiliacion_file)
    af.update_scan_list(None)
    assert af.scan_list is None


def test_reload_if_changed_sin_cambios(afiliacion_file):
    af = AfiliacionConfig(afiliacion_file)
    assert af.reload_if_changed() is False


def test_reload_if_changed_con_cambios(afiliacion_file):
    import time
    af = AfiliacionConfig(afiliacion_file)
    time.sleep(0.05)
    afiliacion_file.write_text(yaml.dump({"afiliacion": {"gssi": "99999", "scan_list": None}}))
    assert af.reload_if_changed() is True
    assert af.gssi == "99999"
    assert af.scan_list is None


def test_save_y_reload(tmp_path):
    path = tmp_path / "afiliacion.yaml"
    af = AfiliacionConfig(path)
    af.gssi = "36005"
    af.scan_list = "TestList"
    af.save()
    af2 = AfiliacionConfig(path)
    assert af2.gssi == "36005"
    assert af2.scan_list == "TestList"


# ---------------------------------------------------------------------------
# Notificaciones Telegram al cambiar afiliación
# ---------------------------------------------------------------------------

def test_update_gssi_notifica_telegram_si_hay_bot(afiliacion_file):
    bot = mock.MagicMock()
    af = AfiliacionConfig(afiliacion_file, bot=bot)
    af.update_gssi("99999")
    bot.notificar_cambio_afiliacion.assert_called_once_with("GSSI", "36001", "99999")


def test_update_gssi_no_notifica_si_mismo_valor(afiliacion_file):
    """Si el GSSI no cambia, no debe notificar."""
    bot = mock.MagicMock()
    af = AfiliacionConfig(afiliacion_file, bot=bot)
    af.update_gssi("36001")  # mismo valor
    bot.notificar_cambio_afiliacion.assert_not_called()


def test_update_gssi_sin_bot_no_falla(afiliacion_file):
    """Sin bot inyectado, update_gssi no debe lanzar excepción."""
    af = AfiliacionConfig(afiliacion_file)  # bot=None por defecto
    af.update_gssi("36002")  # no debe fallar
    assert af.gssi == "36002"


def test_update_scan_list_notifica_telegram_si_hay_bot(afiliacion_file):
    bot = mock.MagicMock()
    af = AfiliacionConfig(afiliacion_file, bot=bot)
    af.update_scan_list("NuevaLista")
    bot.notificar_cambio_afiliacion.assert_called_once_with("Scan List", "ListaScan1", "NuevaLista")


def test_update_scan_list_no_notifica_si_mismo_valor(afiliacion_file):
    bot = mock.MagicMock()
    af = AfiliacionConfig(afiliacion_file, bot=bot)
    af.update_scan_list("ListaScan1")  # mismo valor
    bot.notificar_cambio_afiliacion.assert_not_called()


def test_set_bot_inyecta_correctamente(afiliacion_file):
    af = AfiliacionConfig(afiliacion_file)
    assert af._bot is None
    bot = mock.MagicMock()
    af.set_bot(bot)
    assert af._bot is bot

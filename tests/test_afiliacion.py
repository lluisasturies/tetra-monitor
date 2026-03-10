import os
import sys
import pytest
import yaml

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
    # Verifica persistencia en disco
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
    # Nueva instancia que lee desde disco
    af2 = AfiliacionConfig(path)
    assert af2.gssi == "36005"
    assert af2.scan_list == "TestList"

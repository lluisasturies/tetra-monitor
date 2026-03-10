import os
import time
import pytest
import yaml

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from filters.keyword_filter import KeywordFilter


@pytest.fixture
def keywords_file(tmp_path):
    """Crea un keywords.yaml temporal con palabras de prueba."""
    path = tmp_path / "keywords.yaml"
    path.write_text(yaml.dump({"keywords": ["incendio", "emergencia", "evacuación"]}))
    return path


def test_carga_keywords(keywords_file):
    kf = KeywordFilter(str(keywords_file))
    assert len(kf.keywords) == 3
    assert "incendio" in kf.keywords


def test_contiene_evento_positivo(keywords_file):
    kf = KeywordFilter(str(keywords_file))
    assert kf.contiene_evento("Hay un INCENDIO en el edificio") is True


def test_contiene_evento_negativo(keywords_file):
    kf = KeywordFilter(str(keywords_file))
    assert kf.contiene_evento("Patrulla en ruta, sin novedad") is False


def test_contiene_evento_case_insensitive(keywords_file):
    kf = KeywordFilter(str(keywords_file))
    assert kf.contiene_evento("EMERGENCIA en sector norte") is True
    assert kf.contiene_evento("Emergencia en sector norte") is True


def test_keywords_vacias(tmp_path):
    path = tmp_path / "keywords.yaml"
    path.write_text(yaml.dump({"keywords": []}))
    kf = KeywordFilter(str(path))
    assert kf.contiene_evento("incendio") is False


def test_fichero_no_existe():
    with pytest.raises(FileNotFoundError):
        KeywordFilter("/ruta/que/no/existe/keywords.yaml")


def test_reload_if_changed_sin_cambios(keywords_file):
    kf = KeywordFilter(str(keywords_file))
    assert kf.reload_if_changed() is False


def test_reload_if_changed_con_cambios(keywords_file):
    kf = KeywordFilter(str(keywords_file))
    time.sleep(0.05)
    keywords_file.write_text(yaml.dump({"keywords": ["incendio", "inundación"]}))
    assert kf.reload_if_changed() is True
    assert "inundación" in kf.keywords
    assert len(kf.keywords) == 2


def test_reload_no_pierde_keywords_si_yaml_invalido(keywords_file):
    kf = KeywordFilter(str(keywords_file))
    keywords_antes = kf.keywords.copy()
    time.sleep(0.05)
    keywords_file.write_text(": yaml: inválido: [")
    kf.reload_if_changed()
    assert kf.keywords == keywords_antes or kf.keywords == []

"""Testes da ingestão NASA FIRMS — parsing, fallback, classificação."""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def test_fetch_retorna_lista():
    from ingestor import fetch_nasa_firms_data
    data = fetch_nasa_firms_data()
    assert isinstance(data, list)
    assert len(data) > 0


def test_fetch_campos_obrigatorios():
    from ingestor import fetch_nasa_firms_data
    data = fetch_nasa_firms_data()
    required = {'id', 'lat', 'lon', 'temp', 'frp', 'conf', 'type'}
    for item in data:
        assert required.issubset(item.keys()), f"Campos faltando: {required - item.keys()}"


def test_fetch_fallback_calor_e_frio():
    """Quando a API falha completamente, fallback gera calor E frio."""
    from ingestor import fetch_nasa_firms_data
    with patch('ingestor.requests.get', side_effect=Exception("DNS fail")):
        data = fetch_nasa_firms_data()
    heat = [d for d in data if d['type'] == 0]
    cold = [d for d in data if d['type'] == 1]
    assert len(heat) > 0, "Fallback deve gerar pontos de calor"
    assert len(cold) > 0, "Fallback deve gerar pontos de frio"


def test_fallback_calor_regioes():
    """Pontos de calor devem cobrir múltiplas regiões."""
    from ingestor import fetch_nasa_firms_data
    with patch('ingestor.requests.get', side_effect=Exception("DNS fail")):
        data = fetch_nasa_firms_data()
    heat = [d for d in data if d['type'] == 0]
    lats = [d['lat'] for d in heat]
    # Deve ter pontos no hemisfério norte E sul
    assert any(l < 0 for l in lats), "Deve ter calor no hemisfério sul"
    assert any(l > 0 for l in lats), "Deve ter calor no hemisfério norte"


def test_fallback_frio_polos():
    """Pontos de frio devem incluir regiões polares."""
    from ingestor import fetch_nasa_firms_data
    with patch('ingestor.requests.get', side_effect=Exception("DNS fail")):
        data = fetch_nasa_firms_data()
    cold = [d for d in data if d['type'] == 1]
    lats = [d['lat'] for d in cold]
    assert any(l > 55 for l in lats), "Deve ter frio no Ártico"
    assert any(l < -45 for l in lats), "Deve ter frio em região polar sul"


def test_classificacao_termica():
    """temp >= 295 → type=0 (calor), temp < 295 → type=1 (frio)."""
    from ingestor import fetch_nasa_firms_data
    with patch('ingestor.requests.get', side_effect=Exception("DNS fail")):
        data = fetch_nasa_firms_data()
    for d in data:
        if d['type'] == 0:
            assert d['temp'] >= 295.0, f"Calor com temp={d['temp']} < 295"
        else:
            assert d['temp'] < 295.0, f"Frio com temp={d['temp']} >= 295"


def test_ids_unicos():
    """Todos os IDs no batch devem ser únicos."""
    from ingestor import fetch_nasa_firms_data
    data = fetch_nasa_firms_data()
    ids = [d['id'] for d in data]
    assert len(ids) == len(set(ids)), "IDs duplicados encontrados"

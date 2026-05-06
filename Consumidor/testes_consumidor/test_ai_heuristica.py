"""Testes do fallback_predict — gate de temperatura e scoring."""
import numpy as np
from ai_processor import fallback_predict


def _feat(lat=0, lng=0, frp=0, temp_k=300, conf=50, hour=12, month=6, neighbors=0):
    return (lat, lng, frp, temp_k, conf, hour, month, neighbors)


def test_gate_temperatura_bloqueia():
    result = fallback_predict([_feat(temp_k=280.0)])
    assert result[0] == 0.05


def test_gate_limite_310():
    result = fallback_predict([_feat(temp_k=310.0)])
    assert result[0] > 0.05


def test_temp_360_score_alto():
    result = fallback_predict([_feat(temp_k=360.0, conf=0, frp=0, hour=0, month=1)])
    assert result[0] == 0.50


def test_temp_330_score_medio():
    result = fallback_predict([_feat(temp_k=330.0, conf=0, frp=0, hour=0, month=1)])
    assert result[0] == 0.35


def test_confianca_90_bonus():
    base = fallback_predict([_feat(temp_k=330.0, conf=0, frp=0, hour=0, month=1)])[0]
    com_conf = fallback_predict([_feat(temp_k=330.0, conf=95, frp=0, hour=0, month=1)])[0]
    assert com_conf - base == pytest.approx(0.20, abs=0.01)


def test_confianca_80_bonus():
    base = fallback_predict([_feat(temp_k=330.0, conf=0, frp=0, hour=0, month=1)])[0]
    com_conf = fallback_predict([_feat(temp_k=330.0, conf=85, frp=0, hour=0, month=1)])[0]
    assert com_conf - base == pytest.approx(0.10, abs=0.01)


def test_frp_50_bonus():
    base = fallback_predict([_feat(temp_k=330.0, conf=0, frp=0, hour=0, month=1)])[0]
    com_frp = fallback_predict([_feat(temp_k=330.0, conf=0, frp=60, hour=0, month=1)])[0]
    assert com_frp - base == pytest.approx(0.20, abs=0.01)


def test_horario_pico():
    fora = fallback_predict([_feat(temp_k=330.0, conf=0, frp=0, hour=10, month=1)])[0]
    pico = fallback_predict([_feat(temp_k=330.0, conf=0, frp=0, hour=14, month=1)])[0]
    assert pico - fora == pytest.approx(0.05, abs=0.01)


def test_mes_seco():
    fora = fallback_predict([_feat(temp_k=330.0, conf=0, frp=0, hour=0, month=2)])[0]
    seco = fallback_predict([_feat(temp_k=330.0, conf=0, frp=0, hour=0, month=8)])[0]
    assert seco - fora == pytest.approx(0.05, abs=0.01)


def test_score_maximo_1():
    result = fallback_predict([_feat(temp_k=400, conf=99, frp=100, hour=14, month=8)])
    assert result[0] <= 1.0


import pytest

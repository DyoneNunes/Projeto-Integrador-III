"""Testes do compute_urgency — fórmula e edge cases."""
import math
from ai_processor import compute_urgency


def test_formula_basica():
    # urgency = 0.5*prob + 0.3*(frp/200) + 0.2*((temp-300)/100)
    result = compute_urgency(prob=0.8, frp=100.0, temp_k=350.0)
    expected = 0.5 * 0.8 + 0.3 * (100 / 200) + 0.2 * ((350 - 300) / 100)
    assert math.isclose(result, expected, rel_tol=1e-5)


def test_frp_normalizado_cap():
    # frp=400 → min(400/200, 1.0) = 1.0
    result = compute_urgency(prob=0.0, frp=400.0, temp_k=300.0)
    assert math.isclose(result, 0.3 * 1.0, rel_tol=1e-5)


def test_temp_normalizada_cap():
    # temp_k=500 → min((500-300)/100, 1.0) = 1.0
    result = compute_urgency(prob=0.0, frp=0.0, temp_k=500.0)
    assert math.isclose(result, 0.2 * 1.0, rel_tol=1e-5)


def test_temp_baixa_zero():
    # temp_k=280 → max(280-300, 0) / 100 = 0.0
    result = compute_urgency(prob=0.0, frp=0.0, temp_k=280.0)
    assert result == 0.0


def test_probabilidade_zero():
    result = compute_urgency(prob=0.0, frp=0.0, temp_k=300.0)
    assert result == 0.0

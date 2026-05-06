"""Testes do count_neighbors — distância e auto-exclusão."""
from data_processor import count_neighbors


def test_vizinhos_dentro_raio():
    # Dois pontos a ~0.3° de distância
    records = [
        (-10.0, -50.0, 0, 0, 0, 0, '', '', ''),
        (-10.2, -50.2, 0, 0, 0, 0, '', '', ''),
    ]
    assert count_neighbors(records, 0) == 1.0


def test_vizinhos_fora_raio():
    # Dois pontos a ~1.4° de distância (> 0.5 radius)
    records = [
        (-10.0, -50.0, 0, 0, 0, 0, '', '', ''),
        (-11.0, -51.0, 0, 0, 0, 0, '', '', ''),
    ]
    assert count_neighbors(records, 0) == 0.0


def test_auto_exclusao():
    # Ponto sozinho não conta a si mesmo
    records = [
        (-10.0, -50.0, 0, 0, 0, 0, '', '', ''),
    ]
    assert count_neighbors(records, 0) == 0.0


def test_lista_vazia():
    assert count_neighbors([], 0) == 0.0


def test_multiplos_vizinhos():
    # 5 pontos muito próximos (< 0.1° cada)
    records = [
        (-10.0, -50.0, 0, 0, 0, 0, '', '', ''),
        (-10.01, -50.01, 0, 0, 0, 0, '', '', ''),
        (-10.02, -50.02, 0, 0, 0, 0, '', '', ''),
        (-10.03, -50.03, 0, 0, 0, 0, '', '', ''),
        (-10.04, -50.04, 0, 0, 0, 0, '', '', ''),
    ]
    assert count_neighbors(records, 0) == 4.0

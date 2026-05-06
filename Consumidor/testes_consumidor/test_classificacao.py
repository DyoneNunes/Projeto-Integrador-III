"""Testes da lógica de classificação térmica (calor/frio, severidade)."""

TEMP_ANOMALY_THRESHOLD = 330.0
CONFIDENCE_THRESHOLD = 80


def classify_thermal_type(temp):
    """Reproduz a classificação do ingestor."""
    return 0 if temp >= 295.0 else 1


def classify_severity(temp, conf, sat_type):
    """Reproduz a classificação do data_processor."""
    is_fire = (sat_type == 0)
    is_anomaly = (conf >= CONFIDENCE_THRESHOLD and temp >= TEMP_ANOMALY_THRESHOLD and is_fire)
    if not is_fire:
        return 'LOW'
    elif is_anomaly:
        return 'CRITICAL'
    else:
        return 'INFO'


def test_calor_classificado_type_0():
    assert classify_thermal_type(350.0) == 0


def test_frio_classificado_type_1():
    assert classify_thermal_type(250.0) == 1


def test_limite_exato_295():
    assert classify_thermal_type(295.0) == 0


def test_anomalia_termica_critical():
    assert classify_severity(temp=380.0, conf=95, sat_type=0) == 'CRITICAL'


def test_leitura_estavel_info():
    assert classify_severity(temp=320.0, conf=90, sat_type=0) == 'INFO'


def test_fonte_estatica_low():
    assert classify_severity(temp=380.0, conf=95, sat_type=1) == 'LOW'


def test_baixa_confianca_info():
    assert classify_severity(temp=380.0, conf=50, sat_type=0) == 'INFO'


def test_frio_extremo_low():
    assert classify_severity(temp=220.0, conf=90, sat_type=1) == 'LOW'

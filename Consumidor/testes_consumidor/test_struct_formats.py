"""Testes de pack/unpack roundtrip dos formatos binários."""
import struct
import math


INGESTOR_FORMAT = '=ddddiii'
FEATURE_FORMAT = '=iffffffff'
PREDICTION_FORMAT = '=iiffff'


def test_ingestor_struct_size():
    assert struct.calcsize(INGESTOR_FORMAT) == 44


def test_feature_struct_size():
    assert struct.calcsize(FEATURE_FORMAT) == 36


def test_prediction_struct_size():
    assert struct.calcsize(PREDICTION_FORMAT) == 24


def test_ingestor_struct_roundtrip():
    lat, lon, temp, frp = -10.5, -50.3, 380.0, 35.5
    conf, sat_type, record_id = 95, 0, 12345
    packed = struct.pack(INGESTOR_FORMAT, lat, lon, temp, frp, conf, sat_type, record_id)
    assert len(packed) == 44
    u_lat, u_lon, u_temp, u_frp, u_conf, u_type, u_id = struct.unpack(INGESTOR_FORMAT, packed)
    assert math.isclose(u_lat, lat)
    assert math.isclose(u_lon, lon)
    assert math.isclose(u_temp, temp)
    assert math.isclose(u_frp, frp)
    assert u_conf == conf
    assert u_type == sat_type
    assert u_id == record_id


def test_feature_struct_roundtrip():
    reading_id = 999
    lat, lng, frp, temp_k = -10.5, -50.3, 35.5, 380.0
    conf, hour, month, neighbors = 95.0, 14.0, 8.0, 3.0
    packed = struct.pack(FEATURE_FORMAT, reading_id, lat, lng, frp, temp_k, conf, hour, month, neighbors)
    assert len(packed) == 36
    u = struct.unpack(FEATURE_FORMAT, packed)
    assert u[0] == reading_id
    assert math.isclose(u[1], lat, rel_tol=1e-5)
    assert math.isclose(u[4], temp_k, rel_tol=1e-5)


def test_prediction_struct_roundtrip():
    counter, pred_class = 42, 1
    prob, urgency, lat, lng = 0.85, 0.72, -10.5, -50.3
    packed = struct.pack(PREDICTION_FORMAT, counter, pred_class, prob, urgency, lat, lng)
    assert len(packed) == 24
    u = struct.unpack(PREDICTION_FORMAT, packed)
    assert u[0] == counter
    assert u[1] == pred_class
    assert math.isclose(u[2], prob, rel_tol=1e-5)

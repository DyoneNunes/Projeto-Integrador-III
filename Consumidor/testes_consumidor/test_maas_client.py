"""Testes do MaaSMemory — seek, read, write, boundaries."""
import pytest
from unittest.mock import MagicMock
from maas_client import MaaSMemory


def _make_memory(size=1024):
    stub = MagicMock()
    stub.ReadMemory.return_value = MagicMock(data=b'\x01' * 100)
    stub.WriteMemory.return_value = None
    return MaaSMemory(stub, "test-alloc-id", size)


def test_seek_valid():
    mm = _make_memory(1024)
    mm.seek(0)
    assert mm.pos == 0
    mm.seek(1023)
    assert mm.pos == 1023


def test_seek_invalid():
    mm = _make_memory(1024)
    with pytest.raises(ValueError):
        mm.seek(-1)
    with pytest.raises(ValueError):
        mm.seek(1024)


def test_write_advances_pos():
    mm = _make_memory(1024)
    mm.seek(0)
    mm.write(b'\x00' * 10)
    assert mm.pos == 10


def test_write_overflow():
    mm = _make_memory(100)
    mm.seek(95)
    with pytest.raises(ValueError):
        mm.write(b'\x00' * 10)


def test_read_clips_at_boundary():
    mm = _make_memory(1024)
    mm.seek(1020)
    data = mm.read(100)
    assert len(data) <= 4


def test_read_empty():
    mm = _make_memory(100)
    mm.seek(0)
    data = mm.read(0)
    assert data == b""

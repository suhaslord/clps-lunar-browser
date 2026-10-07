import hashlib
from contextlib import nullcontext

import httpx

import pytest

from backend import setup_terrain as module


@pytest.fixture
def payload(monkeypatch):
    data = b"verified scientific elevation bytes"
    monkeypatch.setattr(module, "DEM_SHA256", hashlib.sha256(data).hexdigest())
    return data


def test_offline_check_and_cached_dataset(monkeypatch, tmp_path, payload):
    path = tmp_path / "dem.tif"
    with pytest.raises(ValueError, match="Missing or incorrect"):
        module.setup_terrain(path, check_only=True)
    path.write_bytes(payload)
    monkeypatch.setattr(module, "download_stream", lambda *_args, **_kwargs: pytest.fail("should stay offline"))
    module.setup_terrain(path, check_only=True)
    module.setup_terrain(path)


def test_download_is_verified_and_atomic(monkeypatch, tmp_path, payload):
    path = tmp_path / "data" / "dem.tif"
    monkeypatch.setattr(module, "download_stream", lambda *_args, **_kwargs: nullcontext(httpx.Response(200, content=payload)))
    module.setup_terrain(path)
    assert path.read_bytes() == payload
    assert list(path.parent.glob("*.part")) == []


def test_truncated_download_retries_without_destroying_existing_file(monkeypatch, tmp_path, payload):
    path = tmp_path / "dem.tif"
    path.write_bytes(b"old")
    responses = iter([b"truncated", payload])
    monkeypatch.setattr(module, "download_stream", lambda *_args, **_kwargs: nullcontext(httpx.Response(200, content=next(responses))))
    module.setup_terrain(path)
    assert path.read_bytes() == payload
    assert not list(tmp_path.glob("*.part"))


def test_failed_download_preserves_existing_file(monkeypatch, tmp_path, payload):
    path = tmp_path / "dem.tif"
    path.write_bytes(b"old")
    monkeypatch.setattr(module, "download_stream", lambda *_args, **_kwargs: nullcontext(httpx.Response(200, content=b"wrong")))
    with pytest.raises(ValueError, match="SHA-256"):
        module.setup_terrain(path)
    assert path.read_bytes() == b"old"
    assert not list(tmp_path.glob("*.part"))

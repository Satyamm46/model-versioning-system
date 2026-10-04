import io
import sys
from pathlib import Path

import joblib
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Fresh database + storage folders for every test."""
    monkeypatch.setenv("MVS_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("MVS_MODEL_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("MVS_DEPLOY_DIR", str(tmp_path / "deployed"))
    monkeypatch.setenv("MVS_LOG_DIR", str(tmp_path / "logs"))
    from backend.main import app
    with TestClient(app) as c:
        yield c


def good_model_bytes() -> bytes:
    buf = io.BytesIO()
    joblib.dump({"kind": "dummy-model", "coef": [0.1, 0.2]}, buf)
    return buf.getvalue()


@pytest.fixture()
def make_model(client):
    def _make(name="Student Performance Predictor"):
        r = client.post("/api/models", json={"name": name, "description": "test",
                                             "model_type": "Random Forest", "created_by": "Satyam"})
        assert r.status_code == 201, r.text
        return r.json()
    return _make


@pytest.fixture()
def upload(client):
    def _upload(model_id, data=None, filename="model.pkl", accuracy=90.0):
        data = good_model_bytes() if data is None else data
        return client.post(f"/api/models/{model_id}/versions",
                           files={"file": (filename, data)},
                           data={"accuracy": str(accuracy), "created_by": "Satyam", "change_notes": "n"})
    return _upload

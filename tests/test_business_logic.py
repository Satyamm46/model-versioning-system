"""Business-rule tests: the rules from the project specification."""
import sqlite3

import pytest

from tests.conftest import good_model_bytes


def statuses(client, model_id):
    return {v["version"]: v["status"] for v in client.get(f"/api/models/{model_id}/versions").json()}


def test_versions_are_numbered_automatically(client, make_model, upload):
    m = make_model()
    assert [upload(m["id"]).json()["version"] for _ in range(3)] == [1, 2, 3]


def test_duplicate_versions_cannot_exist(client, make_model, upload, tmp_path):
    m = make_model()
    upload(m["id"])
    conn = sqlite3.connect(tmp_path / "test.db")
    with pytest.raises(sqlite3.IntegrityError):  # UNIQUE (model_id, version)
        conn.execute("INSERT INTO model_versions (model_id, version, file_path, status, created_by, created_at) "
                     "VALUES (?, 1, 'x', 'DRAFT', 'u', 'now')", (m["id"],))


def test_only_one_production_version(client, make_model, upload):
    m = make_model()
    ids = [upload(m["id"]).json()["id"] for _ in range(3)]
    for vid in ids:
        assert client.post(f"/api/versions/{vid}/promote", json={}).status_code == 200
    s = statuses(client, m["id"])
    assert list(s.values()).count("PRODUCTION") == 1
    assert s == {1: "ARCHIVED", 2: "ARCHIVED", 3: "PRODUCTION"}


def test_database_blocks_two_production_versions(client, make_model, upload, tmp_path):
    m = make_model()
    a, b = upload(m["id"]).json()["id"], upload(m["id"]).json()["id"]
    conn = sqlite3.connect(tmp_path / "test.db")
    conn.execute("UPDATE model_versions SET status='PRODUCTION' WHERE id=?", (a,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE model_versions SET status='PRODUCTION' WHERE id=?", (b,))


def test_rollback_changes_production_version(client, make_model, upload):
    m = make_model()
    v1, v2, v3 = [upload(m["id"]).json()["id"] for _ in range(3)]
    for vid in (v1, v2, v3):
        client.post(f"/api/versions/{vid}/promote", json={})
    client.post(f"/api/models/{m['id']}/rollback", json={})
    assert statuses(client, m["id"]) == {1: "ARCHIVED", 2: "PRODUCTION", 3: "ARCHIVED"}
    # a second rollback continues backwards: v2 -> v1 (never back to the bad v3)
    client.post(f"/api/models/{m['id']}/rollback", json={})
    assert statuses(client, m["id"]) == {1: "PRODUCTION", 2: "ARCHIVED", 3: "ARCHIVED"}


def test_rollback_without_previous_version_fails(client, make_model, upload):
    m = make_model()
    vid = upload(m["id"]).json()["id"]
    client.post(f"/api/versions/{vid}/promote", json={})
    assert client.post(f"/api/models/{m['id']}/rollback", json={}).status_code == 400


def test_failed_versions_cannot_be_promoted(client, make_model, upload):
    m = make_model()
    bad = upload(m["id"], data=b"this is not a model").json()
    assert bad["status"] == "FAILED"
    assert client.post(f"/api/versions/{bad['id']}/promote", json={}).status_code == 400


def test_failed_promotion_keeps_current_production(client, make_model, upload, tmp_path):
    m = make_model()
    good = upload(m["id"]).json()
    bad = upload(m["id"]).json()
    client.post(f"/api/versions/{good['id']}/promote", json={})
    # corrupt v2's file on disk after upload, then try to promote it
    (tmp_path / "models" / bad["file_path"]).write_bytes(b"corrupted")
    assert client.post(f"/api/versions/{bad['id']}/promote", json={}).status_code == 400
    assert statuses(client, m["id"]) == {1: "PRODUCTION", 2: "FAILED"}


def test_invalid_extension_rejected(client, make_model, upload):
    m = make_model()
    assert upload(m["id"], filename="evil.exe").status_code == 400
    assert upload(m["id"], filename="notes.txt").status_code == 400
    assert client.get(f"/api/models/{m['id']}/versions").json() == []


def test_invalid_model_file_is_marked_failed(client, make_model, upload):
    m = make_model()
    r = upload(m["id"], data=b"garbage bytes")
    assert r.status_code == 201 and r.json()["status"] == "FAILED"
    assert "could not be loaded" in r.json()["validation_message"]


def test_oversized_upload_rejected(client, make_model, upload, monkeypatch):
    monkeypatch.setenv("MVS_MAX_UPLOAD_MB", "0.001")  # ~1 KB
    m = make_model()
    assert upload(m["id"], data=b"x" * 5000).status_code == 413


def test_accuracy_must_be_a_percentage(client, make_model, upload):
    m = make_model()
    assert upload(m["id"], accuracy=140).status_code == 400


def test_promote_publishes_file_to_deploy_dir(client, make_model, upload, tmp_path):
    m = make_model()
    vid = upload(m["id"]).json()["id"]
    client.post(f"/api/versions/{vid}/promote", json={})
    live = tmp_path / "deployed" / "student-performance-predictor" / "model.pkl"
    assert live.read_bytes() == good_model_bytes()

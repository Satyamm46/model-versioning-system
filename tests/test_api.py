"""API tests: one test per endpoint family."""


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "UP", "application": "Model Versioning System"}


def test_create_and_list_models(client, make_model):
    m = make_model()
    assert m["name"] == "Student Performance Predictor"
    assert client.get("/api/models").json()[0]["id"] == m["id"]
    assert client.get(f"/api/models/{m['id']}").status_code == 200


def test_create_model_rejects_bad_input(client):
    assert client.post("/api/models", json={"name": ""}).status_code == 422
    assert client.get("/api/models/999").status_code == 404


def test_duplicate_model_name_rejected(client, make_model):
    make_model()
    r = client.post("/api/models", json={"name": "Student Performance Predictor", "created_by": "x"})
    assert r.status_code == 409


def test_upload_and_list_versions(client, make_model, upload):
    m = make_model()
    r = upload(m["id"])
    assert r.status_code == 201
    assert r.json()["version"] == 1 and r.json()["status"] == "TESTING"
    versions = client.get(f"/api/models/{m['id']}/versions").json()
    assert len(versions) == 1
    assert client.get(f"/api/versions/{versions[0]['id']}").json()["model_name"] == m["name"]


def test_promote_endpoint_and_deployment_history(client, make_model, upload):
    m = make_model()
    vid = upload(m["id"]).json()["id"]
    r = client.post(f"/api/versions/{vid}/promote", json={"performed_by": "Satyam"})
    assert r.status_code == 200 and r.json()["status"] == "PRODUCTION"
    history = client.get(f"/api/models/{m['id']}/deployments").json()
    assert history[0]["action"] == "DEPLOYMENT" and history[0]["status"] == "SUCCESS"
    assert history[0]["deployed_by"] == "Satyam"
    assert client.get("/api/deployments").status_code == 200


def test_rollback_endpoint(client, make_model, upload):
    m = make_model()
    v1 = upload(m["id"]).json()["id"]
    v2 = upload(m["id"]).json()["id"]
    client.post(f"/api/versions/{v1}/promote", json={})
    client.post(f"/api/versions/{v2}/promote", json={})
    r = client.post(f"/api/models/{m['id']}/rollback", json={"performed_by": "Satyam", "reason": "bad v2"})
    assert r.status_code == 200
    assert (r.json()["from_version"], r.json()["to_version"]) == (2, 1)
    assert client.get(f"/api/models/{m['id']}/rollbacks").json()[0]["reason"] == "bad v2"


def test_compare_and_dashboard(client, make_model, upload):
    m = make_model()
    upload(m["id"], accuracy=87)
    upload(m["id"], accuracy=91)
    c = client.get(f"/api/models/{m['id']}/compare", params={"a": 1, "b": 2}).json()
    assert c["accuracy_improvement"] == 4.0
    d = client.get("/api/dashboard").json()
    assert d["total_models"] == 1 and d["total_versions"] == 2
    assert d["production_models"] == 0 and d["failed_versions"] == 0


def test_delete_model_blocked_while_in_production(client, make_model, upload):
    m = make_model()
    vid = upload(m["id"]).json()["id"]
    client.post(f"/api/versions/{vid}/promote", json={})
    assert client.delete(f"/api/models/{m['id']}").status_code == 409

from fastapi.testclient import TestClient

from meshradar.demo import build_demo_app


def test_demo_app_seeds_dashboard_data(tmp_path):
    app = build_demo_app(tmp_path / "demo.db")

    with TestClient(app) as client:
        health = client.get("/api/health")
        nodes = client.get("/api/nodes")
        chat = client.get("/api/chat")
        packets = client.get("/api/packets")
        routes = client.get("/api/mesh/routes")

    assert health.status_code == 200
    assert health.json()["collector"]["state"] == "connected"
    assert health.json()["perspective"]["local_node_num"] == 101
    assert len(nodes.json()) >= 10
    assert len(chat.json()) >= 3
    assert len(packets.json()) >= 10
    assert routes.json()["stats"]["total"] >= 2

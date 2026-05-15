import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.server.routes import router


def test_confirmation_endpoint_approves_pending_request():
    app = FastAPI()
    app.state._web_tool_confirmations = {"abc": None}
    app.include_router(router)
    client = TestClient(app)

    response = client.post("/v1/tool-confirmations/abc", json={"approved": True})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "approved": True}
    assert app.state._web_tool_confirmations["abc"] is True


def test_tool_event_payloads_are_json_safe():
    payload = {
        "tool": "create_folder",
        "arguments": '{"path":"C:/tmp/openjarvis-demo"}',
        "success": True,
        "latency": 12.5,
        "result": {"thought": "Created folder"},
    }

    encoded = json.dumps(payload, default=str)
    decoded = json.loads(encoded)

    assert decoded["tool"] == "create_folder"
    assert "result" in decoded

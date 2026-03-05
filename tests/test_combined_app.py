import importlib
import os
import sys

from fastapi.testclient import TestClient

os.environ.setdefault("CONN_STR", "postgresql://dummy:dummy@localhost/dummy")


def test_server_dashscope_import_is_cli_safe(monkeypatch):
    """
    Importing server_dashscope should not invoke tyro.cli at module import time.
    """
    import tyro

    monkeypatch.setattr(
        tyro,
        "cli",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("tyro.cli must not run during module import")
        ),
    )
    sys.modules.pop("fastapi_server.server_dashscope", None)

    module = importlib.import_module("fastapi_server.server_dashscope")
    assert module.app is not None
    assert module.dashscope_router is not None


def test_combined_app_serves_front_and_dashscope_routes():
    from fastapi_server.combined import app

    client = TestClient(app)

    # front_apis route should be available.
    front_resp = client.get("/v1/pipelines/graphs")
    assert front_resp.status_code == 200, front_resp.text
    assert "available_graphs" in front_resp.json()

    # DashScope route should exist at the same path (missing auth should not be 404).
    dash_resp = client.post(
        "/api/v1/apps/blueberry/sessions/test-session/responses",
        json={"input": {"prompt": "hello"}, "stream": False},
    )
    assert dash_resp.status_code != 404, dash_resp.text


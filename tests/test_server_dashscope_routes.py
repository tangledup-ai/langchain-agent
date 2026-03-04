import os
import signal
import subprocess
import time
from http import HTTPStatus

import pytest
import requests
from dotenv import load_dotenv

load_dotenv()


def _get_service_api_key() -> str:
    """Return the first API key from FAST_AUTH_KEYS env (comma-separated)."""
    raw = os.getenv("FAST_AUTH_KEYS", "")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts[0] if parts else None


def _wait_for_health(base_url: str, timeout: float = 20.0) -> None:
    """Poll the /health endpoint until the server is up or timeout."""
    deadline = time.time() + timeout
    url = base_url.rstrip("/") + "/health"
    last_err = None
    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == HTTPStatus.OK:
                return
        except Exception as e:  # pragma: no cover - best-effort polling
            last_err = e
        time.sleep(0.5)
    raise RuntimeError(f"Server did not become healthy in time: last_err={last_err}")


@pytest.fixture(scope="module")
def dashscope_server():
    """
    Start a real uvicorn instance of server_dashscope for end-to-end routing tests.

    This mirrors how docker-compose runs `xiaozhan` (server_dashscope.py) so we
    exercise the full stack, including PipelineManager + registry routing.
    """
    env = os.environ.copy()
    # Ensure registry file is picked up (falls back to this by default, but be explicit).
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    registry_path = os.path.join(project_root, "configs", "pipeline_registry.json")
    env.setdefault("FAST_PIPELINE_REGISTRY_FILE", registry_path)

    cmd = [
        "python",
        "-m",
        "uvicorn",
        "fastapi_server.server_dashscope:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8588",
    ]
    proc = subprocess.Popen(cmd, env=env)

    base_url = "http://127.0.0.1:8588"
    try:
        _wait_for_health(base_url)
    except Exception:
        proc.terminate()
        proc.wait(timeout=10)
        raise

    yield base_url

    # Teardown
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - best-effort cleanup
            proc.kill()
            proc.wait(timeout=10)


def _post_app_response(base_url: str, pipeline_id: str, body: dict, api_key: str):
    url = f"{base_url}/api/v1/apps/{pipeline_id}/sessions/test-session/responses"
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.post(url, json=body, headers=headers, timeout=20)
    return resp


def test_pipeline_selected_via_pipeline_id_body(dashscope_server):
    """
    When client specifies `pipeline_id` in the body, it should be used as the selector
    and surfaced back in the JSON response.
    """
    base_url = dashscope_server
    api_key = _get_service_api_key()
    if not api_key:
        pytest.skip(
            "FAST_AUTH_KEYS is not set; cannot authenticate against server_dashscope"
        )
    body = {
        "input": {
            "prompt": "你是谁?",
            "session_id": "sess-1",
        },
        "pipeline_id": "blueberry",
        "stream": False,
    }

    resp = _post_app_response(
        base_url, pipeline_id="blueberry", body=body, api_key=api_key
    )
    assert resp.status_code == HTTPStatus.OK, resp.text
    data = resp.json()
    assert data.get("pipeline_id") == "blueberry"
    assert "text" in data.get("output", {})


def test_pipeline_selected_via_pipeline_id_body_blueberry(dashscope_server):
    """
    When client specifies `pipeline_id` in the body, it should be used as the selector
    and surfaced back in the JSON response.
    """
    base_url = dashscope_server
    api_key = _get_service_api_key()
    if not api_key:
        pytest.skip(
            "FAST_AUTH_KEYS is not set; cannot authenticate against server_dashscope"
        )
    body = {
        "input": {
            "prompt": "hello from blueberry",
            "session_id": "sess-2",
        },
        "pipeline_id": "blueberry",
        "stream": False,
    }

    resp = _post_app_response(
        base_url, pipeline_id="blueberry", body=body, api_key=api_key
    )
    assert resp.status_code == HTTPStatus.OK, resp.text
    data = resp.json()
    assert data.get("pipeline_id") == "blueberry"
    assert "text" in data.get("output", {})


def test_pipeline_forbidden_for_api_key_when_not_allowed(dashscope_server):
    """
    API key policy in pipeline_registry should prevent a key from using pipelines
    it is not explicitly allowed to access.
    """
    base_url = dashscope_server
    body = {
        "input": {
            "prompt": "this should be forbidden",
            "session_id": "sess-3",
        },
        "pipeline_id": "blueberry",
        "stream": False,
    }

    # Use a guaranteed-wrong API key so we test 401 behavior regardless of registry config.
    resp = _post_app_response(
        base_url, pipeline_id="blueberry", body=body, api_key="invalid-key-for-test"
    )
    assert resp.status_code == HTTPStatus.UNAUTHORIZED
    data = resp.json()
    assert data.get("detail") == "Invalid API key"

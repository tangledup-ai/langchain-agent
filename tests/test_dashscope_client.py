#!/usr/bin/env python3
"""
Minimal test for DashScope Application.call against server_dashscope.py

Instructions:
- Start the DashScope-compatible server first, e.g.:
    uvicorn fastapi_server.server_dashscope:app --host 0.0.0.0 --port 8588 --reload
- Set BASE_URL below to the server base URL you started.
- Optionally set environment variables ALI_API_KEY and ALI_APP_ID.
"""

import os
import json
import os.path as osp
import uuid
from dotenv import load_dotenv
from loguru import logger
from http import HTTPStatus

TAG = __name__

load_dotenv()

try:
    from dashscope import Application
    import dashscope
except Exception as e:
    print("dashscope package not found. Please install it: pip install dashscope")
    raise


# <<< Paste your running FastAPI base url here >>>
BASE_URL = os.getenv("DS_BASE_URL", "http://127.0.0.1:8500/api/")


# Params
def _first_non_empty_csv_token(value: str) -> str:
    parts = [p.strip() for p in (value or "").split(",") if p.strip()]
    return parts[0] if parts else ""


def _load_registry() -> dict:
    project_root = osp.dirname(osp.dirname(osp.abspath(__file__)))
    registry_path = os.getenv(
        "FAST_PIPELINE_REGISTRY_FILE",
        osp.join(project_root, "configs", "pipeline_registry.json"),
    )
    with open(registry_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _pick_api_key(registry: dict) -> str:
    # For local server_dashscope testing, FAST_AUTH_KEYS is usually the server auth source.
    fast_first = _first_non_empty_csv_token(os.getenv("FAST_AUTH_KEYS", ""))
    ali_key = (os.getenv("ALI_API_KEY") or "").strip()

    api_policies = registry.get("api_keys") or {}
    if fast_first and (not api_policies or fast_first in api_policies):
        return fast_first
    if ali_key and (not api_policies or ali_key in api_policies):
        return ali_key
    if fast_first:
        return fast_first
    if ali_key:
        return ali_key
    raise RuntimeError(
        "Missing API key. Set FAST_AUTH_KEYS or ALI_API_KEY in your environment."
    )


def _pick_app_id(api_key: str, registry: dict) -> str:
    if api_key:
        explicit = (registry.get("api_keys") or {}).get(api_key, {}).get("app_id")
        if explicit:
            return explicit

    pipelines_obj = registry.get("pipelines")
    if not isinstance(pipelines_obj, dict):
        pipelines_obj = {}
    pipeline_ids = [r for r in pipelines_obj.keys() if isinstance(r, str) and r]

    if pipeline_ids:
        return pipeline_ids[0]
    return "default"


def _warn_if_policy_disallows_app_id(api_key: str, app_id: str, registry: dict) -> None:
    policy = (registry.get("api_keys") or {}).get(api_key, {})
    if not isinstance(policy, dict):
        return
    allowed = policy.get("allowed_pipeline_ids")
    if isinstance(allowed, list) and allowed and app_id not in allowed:
        logger.bind(tag=TAG).warning(
            f"app_id='{app_id}' is not in allowed_pipeline_ids for current API key; server may return 403."
        )


REGISTRY = _load_registry()
API_KEY = _pick_api_key(REGISTRY)
APP_ID = _pick_app_id(API_KEY, REGISTRY)
_warn_if_policy_disallows_app_id(API_KEY, APP_ID, REGISTRY)
SESSION_ID = str(uuid.uuid4())

dialogue = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "你叫什么名字"},
]

call_params = {
    "api_key": API_KEY,
    "app_id": APP_ID,
    "session_id": SESSION_ID,
    "messages": dialogue,
    "stream": True,
}


def main():
    # Point the SDK to our FastAPI implementation
    if BASE_URL and ("/api/" in BASE_URL):
        dashscope.base_http_api_url = BASE_URL
    # Some SDK paths rely on global api_key to build Authorization header.
    dashscope.api_key = API_KEY
    # dashscope.base_http_api_url = BASE_URL
    print(f"Using base_http_api_url = {dashscope.base_http_api_url}")
    print(f"Using app_id = {APP_ID}")

    print("\nCalling Application.call(stream=True)...\n")
    responses = Application.call(**call_params)

    try:
        last_text = ""
        u = ""
        for resp in responses:
            if resp.status_code != HTTPStatus.OK:
                logger.bind(tag=TAG).error(
                    f"code={resp.status_code}, message={resp.message}, 请参考文档：https://help.aliyun.com/zh/model-studio/developer-reference/error-code"
                )
                continue
            current_text = getattr(getattr(resp, "output", None), "text", None)
            if current_text is None:
                continue
            # SDK流式为增量覆盖，计算差量输出
            if len(current_text) >= len(last_text):
                delta = current_text[len(last_text) :]
            else:
                # 避免偶发回退
                delta = current_text
            if delta:
                u = delta
            last_text = current_text

            # For streaming responses, print incrementally to stdout and flush
            # so the user can see tokens as they arrive.
            print(u, end="", flush=True)
    except TypeError:
        # 非流式回落（一次性返回）
        if responses.status_code != HTTPStatus.OK:
            logger.bind(tag=TAG).error(
                f"code={responses.status_code}, message={responses.message}, 请参考文档：https://help.aliyun.com/zh/model-studio/developer-reference/error-code"
            )
            u = "【阿里百练API服务响应异常】"
        else:
            full_text = getattr(getattr(responses, "output", None), "text", "")
            logger.bind(tag=TAG).info(
                f"【阿里百练API服务】完整响应长度: {len(full_text)}"
            )
            u = full_text
            print("from non-stream: ", u)
    except Exception as e:
        logger.bind(tag=TAG).error(f"Error: {e}")
        u = "【阿里百练API服务响应异常】"


if __name__ == "__main__":
    main()

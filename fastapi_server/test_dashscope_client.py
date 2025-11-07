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
BASE_URL = os.getenv("DS_BASE_URL", "http://127.0.0.1:8588/api/")

# Params
API_KEY = "salkjhglakshfs" #os.getenv("ALI_API_KEY", "test-key")
APP_ID = os.getenv("ALI_APP_ID", "test-app")
SESSION_ID = str(uuid.uuid4())

dialogue = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Say 'the world is awesome and beautiful'."},
]

call_params = {
    "api_key": "test_key",
    "app_id": "test_app",
    "session_id": "123",
    "messages": dialogue,
    "stream": True,
}


def main():
    # Point the SDK to our FastAPI implementation
    if BASE_URL and ("/api/" in BASE_URL):
        dashscope.base_http_api_url = BASE_URL
    # dashscope.base_http_api_url = BASE_URL
    print(f"Using base_http_api_url = {dashscope.base_http_api_url}")

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
                delta = current_text[len(last_text):]
            else:
                # 避免偶发回退
                delta = current_text
            if delta:
                u =  delta
            last_text = current_text

            print("from stream: ", u)
    except TypeError:
        # 非流式回落（一次性返回）
        if responses.status_code != HTTPStatus.OK:
            logger.bind(tag=TAG).error(
                f"code={responses.status_code}, message={responses.message}, 请参考文档：https://help.aliyun.com/zh/model-studio/developer-reference/error-code"
            )
            u =  "【阿里百练API服务响应异常】"
        else:
            full_text = getattr(getattr(responses, "output", None), "text", "")
            logger.bind(tag=TAG).info(
                f"【阿里百练API服务】完整响应长度: {len(full_text)}"
            )
            u = full_text
            print("from non-stream: ", u)
    except Exception as e:
        logger.bind(tag=TAG).error(f"Error: {e}")
        u =  "【阿里百练API服务响应异常】"
            


if __name__ == "__main__":
    main()



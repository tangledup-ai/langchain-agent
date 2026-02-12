from typing import Dict, List, Optional
import os
import subprocess

def build_route(pipeline_id:str,
                prompt_set:str,
                tool_keys:List[str],
                port:str,
                api_key: str,
                fast_auth_keys: Optional[str] = None,
                entry_pnt:str="fastapi_server/server_dashscope.py",
                llm_name:str="qwen-plus"):
    cmd = [
        "python", entry_pnt,
        "--port", str(port),
        "route",            # ------------
        "--llm-name", llm_name,
        "--api-key", api_key,
        "--pipeline-id", pipeline_id,
        "--prompt-set-id", prompt_set,
        "tool_node",        # ------------
        "--llm-name", llm_name,
        "--api-key", api_key,
        "--pipeline-id", pipeline_id,
        "--prompt-set-id", prompt_set,
        ]
    if tool_keys:
        cmd.extend(
            ["--tool-manager-config.client-tool-manager.tool-keys", *tool_keys]
        )
    env: Dict[str, str] = os.environ.copy()
    if fast_auth_keys:
        env["FAST_AUTH_KEYS"] = fast_auth_keys
    sv_prc = subprocess.Popen(cmd, env=env)

    return sv_prc, f"http://127.0.0.1:{port}/api/"


def build_react(pipeline_id:str,
                prompt_set:str,
                tool_keys:List[str],
                port:str,
                api_key: str,
                fast_auth_keys: Optional[str] = None,
                entry_pnt:str="fastapi_server/server_dashscope.py",
                llm_name:str="qwen-plus"):
    cmd = [
        "python", entry_pnt,
        "--port", str(port),
        "react",            # ------------
        "--llm-name", llm_name,
        "--api-key", api_key,
        "--pipeline-id", pipeline_id,
        "--prompt-set-id", prompt_set,
        ]
    if tool_keys:
        cmd.extend(
            ["--tool-manager-config.client-tool-manager.tool-keys", *tool_keys]
        )
    env: Dict[str, str] = os.environ.copy()
    if fast_auth_keys:
        env["FAST_AUTH_KEYS"] = fast_auth_keys
    sv_prc = subprocess.Popen(cmd, env=env)

    return sv_prc, f"http://127.0.0.1:{port}/api/"

# {pipeline_id: build_function}
GRAPH_BUILD_FNCS = {
    "routing": build_route,
    "react": build_react,
}
from typing import List
import subprocess

def build_route(pipeline_id:str,
                prompt_set:str,
                tool_keys:List[str],
                port:str,
                api_key: str,
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
    sv_prc = subprocess.Popen(cmd)

    return sv_prc, f"http://0.0.0.0:{port}"


def build_react(pipeline_id:str,
                prompt_set:str,
                tool_keys:List[str],
                port:str,
                api_key: str,
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
    sv_prc = subprocess.Popen(cmd)

    return sv_prc, f"http://0.0.0.0:{port}"

# {pipeline_id: build_function}
GRAPH_BUILD_FNCS = {
    "routing": build_route,
    "react": build_react,
}
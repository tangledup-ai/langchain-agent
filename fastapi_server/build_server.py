from typing import List
import subprocess

def build_route(pipelin_id:str,
                prompt_set:str,
                tool_keys:List[str],
                port:str,
                entry_pnt:str="fastapi_server/server_dashscope.py",
                llm_name:str="qwen-plus",):
    sv_prc = subprocess(
        "python", entry_pnt,
        "--llm-name", llm_name,
        "--port", port,
        "route",
        "--pipeline-id", pipelin_id,
        "--prompt-set-id", prompt_set,
        "--tool-manager-config.client-tool-manager.tool-keys", tool_keys,
    )

    return sv_prc
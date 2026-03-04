from typing import Dict, List, Optional
import os
import os.path as osp
import subprocess
import json

from lang_agent.config.core_config import load_tyro_conf

def opt_to_config(save_path:str, *nargs):
    os.makedirs(osp.dirname(save_path), exist_ok=True)
    subprocess.run(["python", "--save-path", save_path, *nargs])


def _build_and_load_pipeline_config(pipeline_id: str,
                                    pipeline_config_dir: str,
                                    cmd: List[str]):
    save_config_f = osp.join(pipeline_config_dir, f"{pipeline_id}.yml")
    opt_to_config(save_config_f, *cmd)

    # TODO: think if returning the built pipeline is better or just the config obj for front_api
    return load_tyro_conf(save_config_f)


def update_pipeline_registry(pipeline_id:str, 
                             prompt_set:str,
                             registry_f:str="configs/pipeline_registry.json"):
    with open(registry_f, "r") as f:
        registry = json.load(f)
    
    if pipeline_id not in registry["routes"]:
        registry["routes"][pipeline_id] = {
            "enabled": True,
            "config_file": None,
            "prompt_pipeline_id": prompt_set,
        }
    else:
        registry["routes"][pipeline_id]["prompt_pipeline_id"] = prompt_set

    with open(registry_f, "w") as f:
        json.dump(registry, f, indent=4)


def build_route(pipeline_id:str,
                prompt_set:str,
                tool_keys:List[str],
                api_key: str,
                entry_pnt:str="fastapi_server/server_dashscope.py",
                llm_name:str="qwen-plus",
                pipeline_config_dir="configs/pipelines"):
    cmd = [
        "python", entry_pnt,
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

    return _build_and_load_pipeline_config(pipeline_id, pipeline_config_dir, cmd)


def build_react(pipeline_id:str,
                prompt_set:str,
                tool_keys:List[str],
                api_key: str,
                entry_pnt:str="fastapi_server/server_dashscope.py",
                llm_name:str="qwen-plus",
                pipeline_config_dir="configs/pipelines"):
    cmd = [
        "python", entry_pnt,
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

    return _build_and_load_pipeline_config(pipeline_id, pipeline_config_dir, cmd)


# {pipeline_id: build_function}
GRAPH_BUILD_FNCS = {
    "routing": build_route,
    "react": build_react,
}
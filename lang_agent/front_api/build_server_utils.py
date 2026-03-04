from typing import Dict, List, Optional
import os
import os.path as osp
import subprocess
import json

from lang_agent.config.core_config import load_tyro_conf

def opt_to_config(save_path:str, *nargs):
    os.makedirs(osp.dirname(save_path), exist_ok=True)
    subprocess.run(["python", "lang_agent/config/ty_build_config.py", 
                    "--save-path", save_path, *nargs])

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
                llm_name:str="qwen-plus",
                pipeline_config_dir="configs/pipelines"):
    cmd_opt = [
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
        cmd_opt.extend(
            ["--tool-manager-config.client-tool-manager.tool-keys", *tool_keys]
        )

    return _build_and_load_pipeline_config(pipeline_id, pipeline_config_dir, cmd_opt)


def build_react(pipeline_id:str,
                prompt_set:str,
                tool_keys:List[str],
                api_key: str,
                llm_name:str="qwen-plus",
                pipeline_config_dir="configs/pipelines"):
    cmd_opt = [
        "react",            # ------------
        "--llm-name", llm_name,
        "--api-key", api_key,
        "--pipeline-id", pipeline_id,
        "--prompt-set-id", prompt_set,
        ]
    if tool_keys:
        cmd_opt.extend(
            ["--tool-manager-config.client-tool-manager.tool-keys", *tool_keys]
        )

    return _build_and_load_pipeline_config(pipeline_id, pipeline_config_dir, cmd_opt)


# {pipeline_id: build_function}
GRAPH_BUILD_FNCS = {
    "routing": build_route,
    "react": build_react,
}
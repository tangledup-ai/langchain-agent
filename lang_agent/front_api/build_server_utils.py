from typing import Any, Dict, List
import os
import os.path as osp
import subprocess
import json

from lang_agent.config.core_config import load_tyro_conf

_PROJECT_ROOT = osp.dirname(osp.dirname(osp.dirname(osp.abspath(__file__))))
_TY_BUILD_SCRIPT = osp.join(_PROJECT_ROOT, "lang_agent", "config", "ty_build_config.py")


def opt_to_config(save_path: str, *nargs):
    os.makedirs(osp.dirname(save_path), exist_ok=True)
    subprocess.run(
        ["python", _TY_BUILD_SCRIPT, "--save-path", save_path, *nargs],
        check=True,
        cwd=_PROJECT_ROOT,
    )

def _build_and_load_pipeline_config(pipeline_id: str,
                                    pipeline_config_dir: str,
                                    cmd: List[str]):
    save_config_f = osp.join(pipeline_config_dir, f"{pipeline_id}.yml")
    opt_to_config(save_config_f, *cmd)

    # TODO: think if returning the built pipeline is better or just the config obj for front_api
    return load_tyro_conf(save_config_f)


def update_pipeline_registry(pipeline_id:str, # the agent name -- xiaozhan, blueberry
                             prompt_set:str,  # the version of the prompt for xiaozhan/blueberry
                             graph_id: str,   # what type of graph is this pipeline.
                             config_file: str,
                             llm_name: str,
                             enabled: bool = True,
                             registry_f:str="configs/pipeline_registry.json"):
    if not osp.isabs(registry_f):
        registry_f = osp.join(_PROJECT_ROOT, registry_f)
    os.makedirs(osp.dirname(registry_f), exist_ok=True)
    if not osp.exists(registry_f):
        with open(registry_f, "w", encoding="utf-8") as f:
            json.dump({"routes": {}, "api_keys": {}}, f, indent=4)

    with open(registry_f, "r") as f:
        registry = json.load(f)

    routes: Dict[str, Dict[str, Any]] = registry.setdefault("routes", {})
    route = routes.setdefault(pipeline_id, {})
    route["enabled"] = bool(enabled)
    route["config_file"] = config_file
    route["prompt_pipeline_id"] = prompt_set
    route["graph_id"] = graph_id
    route["overrides"] = {"llm_name": llm_name}

    with open(registry_f, "w", encoding="utf-8") as f:
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
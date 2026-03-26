from typing import Any, Dict, List, Literal, Optional
import os
import os.path as osp
import subprocess
import json

from lang_agent.config.core_config import load_tyro_conf
from lang_agent.config.constants import TY_BUILD_SCRIPT, _PROJECT_ROOT

_DEEP_AGENT_BACKEND_ALIASES = {
    "state_bk": "statebk",
    "statebk": "statebk",
    "local_shell": "localshell",
    "localshell": "localshell",
    "daytona_sandbox": "daytonasandbox",
    "daytonasandbox": "daytonasandbox",
}


def opt_to_config(save_path: str, *nargs):
    os.makedirs(osp.dirname(save_path), exist_ok=True)
    subprocess.run(
        ["python", TY_BUILD_SCRIPT, "--save-path", save_path, *nargs],
        check=True,
        cwd=_PROJECT_ROOT,
    )


def _build_and_load_pipeline_config(
    pipeline_id: str, pipeline_config_dir: str, cmd: List[str]
):
    save_config_f = osp.join(pipeline_config_dir, f"{pipeline_id}.yaml")
    opt_to_config(save_config_f, *cmd)

    return load_tyro_conf(save_config_f)


def update_pipeline_registry(
    pipeline_id: str,
    graph_id: str,
    config_file: str,
    llm_name: str,
    enabled: bool = True,
    registry_f: str = "configs/pipeline_registry.json",
):
    if not osp.isabs(registry_f):
        registry_f = osp.join(_PROJECT_ROOT, registry_f)
    os.makedirs(osp.dirname(registry_f), exist_ok=True)
    if not osp.exists(registry_f):
        with open(registry_f, "w", encoding="utf-8") as f:
            json.dump({"pipelines": {}, "api_keys": {}}, f, indent=4)

    with open(registry_f, "r") as f:
        registry = json.load(f)

    pipelines: Dict[str, Dict[str, Any]] = registry.setdefault("pipelines", {})
    pipeline = pipelines.setdefault(pipeline_id, {})
    pipeline["enabled"] = bool(enabled)
    pipeline["config_file"] = config_file
    pipeline["graph_id"] = graph_id
    pipeline["llm_name"] = llm_name

    with open(registry_f, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=4)


def build_route(
    pipeline_id: str,
    prompt_set: str,
    tool_keys: List[str],
    api_key: str,
    llm_name: str = "qwen-plus",
    pipeline_config_dir: str = "configs/pipelines",
    **_: Any,
):
    cmd_opt = [
        "--pipeline.pipeline-id",
        pipeline_id,
        "--pipeline.llm-name", 
        llm_name,
        "route",  # ------------
        "--llm-name",
        llm_name,
        "--api-key",
        api_key,
        "--pipeline-id",
        pipeline_id,
        "--prompt-set-id",
        prompt_set,
    ]

    if tool_keys:
        cmd_opt.extend(
            ["--tool-manager-config.client-tool-manager.tool-keys", *tool_keys]
        )
        # Tyro parses list options greedily across positional subcommands; repeat a
        # parent-level option to terminate list parsing before `tool_node`.
        cmd_opt.extend(["--pipeline-id", pipeline_id])

    cmd_opt.extend(
        [
            "tool_node",  # ------------
            "--llm-name",
            llm_name,
            "--api-key",
            api_key,
            "--pipeline-id",
            pipeline_id,
            "--prompt-set-id",
            prompt_set,
        ]
    )

    return _build_and_load_pipeline_config(pipeline_id, pipeline_config_dir, cmd_opt)


def build_react(
    pipeline_id: str,
    prompt_set: str,
    tool_keys: List[str],
    api_key: str,
    llm_name: str = "qwen-plus",
    pipeline_config_dir: str = "configs/pipelines",
    **_: Any,
):
    cmd_opt = [
        "--pipeline.pipeline-id",
        pipeline_id,
        "--pipeline.llm-name", 
        llm_name,
        "react",  # ------------
        "--llm-name",
        llm_name,
        "--api-key",
        api_key,
        "--pipeline-id",
        pipeline_id,
        "--prompt-set-id",
        prompt_set,
    ]
    if tool_keys:
        cmd_opt.extend(
            ["--tool-manager-config.client-tool-manager.tool-keys", *tool_keys]
        )

    return _build_and_load_pipeline_config(pipeline_id, pipeline_config_dir, cmd_opt)


def build_deep_agent(
    pipeline_id: str,
    prompt_set: str,
    tool_keys: List[str],
    api_key: str,
    llm_name: str = "qwen-plus",
    pipeline_config_dir: str = "configs/pipelines",
    act_bkend: Literal[
        "local_shell",
        "localshell",
        "state_bk",
        "statebk",
        "daytona_sandbox",
        "daytonasandbox",
    ] = "state_bk",
    file_backend_config: Optional[Dict[str, Any]] = None,
    **_: Any,
):
    backend_subcommand = _DEEP_AGENT_BACKEND_ALIASES.get(act_bkend)
    if backend_subcommand is None:
        raise ValueError(
            "Unsupported deepagent backend "
            f"'{act_bkend}'. Expected one of {sorted(_DEEP_AGENT_BACKEND_ALIASES.keys())}"
        )

    cmd_opt = [
        "--pipeline.pipeline-id",
        pipeline_id,
        "--pipeline.llm-name", 
        llm_name,
        "deepagent",
        "--llm-name",
        llm_name,
        "--api-key",
        api_key,
        "--pipeline-id",
        pipeline_id,
        "--prompt-set-id",
        prompt_set,
    ]

    if tool_keys:
        cmd_opt.extend(
            ["--tool-manager-config.client-tool-manager.tool-keys", *tool_keys]
        )
        cmd_opt.extend(["--pipeline-id", pipeline_id])

    cmd_opt.append(backend_subcommand)

    if file_backend_config:
        if "skills_dir" in file_backend_config and file_backend_config["skills_dir"]:
            cmd_opt.extend(["--skills-dir", file_backend_config["skills_dir"]])
        if (
            "rt_skills_dir" in file_backend_config
            and file_backend_config["rt_skills_dir"]
        ):
            cmd_opt.extend(["--rt-skills-dir", file_backend_config["rt_skills_dir"]])
        if (
            "workspace_dir" in file_backend_config
            and file_backend_config["workspace_dir"]
        ):
            cmd_opt.extend(["--workspace-dir", file_backend_config["workspace_dir"]])
        if "api_key" in file_backend_config and file_backend_config["api_key"]:
            cmd_opt.extend(["--api-key", file_backend_config["api_key"]])

    return _build_and_load_pipeline_config(pipeline_id, pipeline_config_dir, cmd_opt)


def build_hybrid_rag(
    pipeline_id: str,
    prompt_set: str,
    tool_keys: List[str],
    api_key: str,
    llm_name: str = "qwen-plus",
    pipeline_config_dir: str = "configs/pipelines",
    **_: Any,
):
    cmd_opt = [
        "--pipeline.pipeline-id",
        pipeline_id,
        "--pipeline.llm-name", 
        llm_name,
        "hybrid_rag",  # ------------
        "--llm-name",
        llm_name,
        "--api-key",
        api_key,
        "--pipeline-id",
        pipeline_id,
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
    "deepagent": build_deep_agent,
}

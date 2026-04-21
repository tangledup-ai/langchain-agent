from typing import Any, Dict, List, Literal, Optional
import os
import os.path as osp
import subprocess
import json
from pathlib import Path

from loguru import logger

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


def _normalize_registry_path(registry_f: str) -> str:
    if osp.isabs(registry_f):
        return registry_f
    return osp.join(_PROJECT_ROOT, registry_f)


def _normalize_pipeline_config_dir(
    registry_f: str, pipeline_config_dir: Optional[str] = None
) -> str:
    if pipeline_config_dir:
        if osp.isabs(pipeline_config_dir):
            return pipeline_config_dir
        return osp.join(_PROJECT_ROOT, pipeline_config_dir)
    return osp.join(osp.dirname(registry_f), "pipelines")


def _graph_id_from_loaded_config(loaded_cfg: Any) -> str:
    graph_config = getattr(loaded_cfg, "graph_config", None)
    graph_names = [
        type(graph_config).__name__.lower(),
        getattr(getattr(graph_config, "_target", None), "__name__", "").lower(),
    ]

    for name in graph_names:
        if "deepagent" in name:
            return "deepagent"
        if "routing" in name:
            return "routing"
        if "react" in name:
            return "react"
        if "hybrid" in name and "rag" in name:
            return "hybrid_rag"

    return "routing"


def _relative_config_path(config_path: str) -> str:
    abs_path = Path(config_path).resolve()
    root = Path(_PROJECT_ROOT).resolve()
    try:
        return abs_path.relative_to(root).as_posix()
    except ValueError:
        return str(abs_path)


def sync_pipeline_registry_from_configs(
    registry_f: str = "configs/pipeline_registry.json",
    pipeline_config_dir: Optional[str] = None,
) -> bool:
    registry_path = _normalize_registry_path(registry_f)
    config_dir = _normalize_pipeline_config_dir(registry_path, pipeline_config_dir)

    os.makedirs(osp.dirname(registry_path), exist_ok=True)
    if not osp.exists(registry_path):
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump({"pipelines": {}, "api_keys": {}}, f, indent=4)
            f.write("\n")

    with open(registry_path, "r", encoding="utf-8") as f:
        registry = json.load(f)

    pipelines: Dict[str, Dict[str, Any]] = registry.setdefault("pipelines", {})
    registry.setdefault("api_keys", {})
    changed = False

    if not osp.isdir(config_dir):
        return False

    config_paths = sorted(
        list(Path(config_dir).glob("*.yaml")) + list(Path(config_dir).glob("*.yml"))
    )

    for config_path in config_paths:
        try:
            loaded_cfg = load_tyro_conf(str(config_path))
        except Exception as exc:
            logger.warning("Skipping pipeline config {} during registry sync: {}", config_path, exc)
            continue

        pipeline_id = str(getattr(loaded_cfg, "pipeline_id", "") or config_path.stem).strip()
        if not pipeline_id:
            logger.warning("Skipping pipeline config without pipeline_id: {}", config_path)
            continue

        llm_name = str(
            getattr(loaded_cfg, "llm_name", None)
            or getattr(getattr(loaded_cfg, "graph_config", None), "llm_name", None)
            or "unknown"
        ).strip()
        graph_id = _graph_id_from_loaded_config(loaded_cfg)
        config_file = _relative_config_path(str(config_path))

        existing = pipelines.get(pipeline_id, {}) if isinstance(pipelines.get(pipeline_id), dict) else {}
        next_spec = {
            "enabled": bool(existing.get("enabled", True)),
            "config_file": config_file,
            "graph_id": graph_id,
            "llm_name": llm_name,
        }

        if existing != next_spec:
            pipelines[pipeline_id] = next_spec
            changed = True

    if changed:
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=4)
            f.write("\n")

    return changed


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
    registry_f = _normalize_registry_path(registry_f)
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
    base_url: Optional[str] = None,
    **_: Any,
):
    cmd_opt = [
        "--pipeline.pipeline-id",
        pipeline_id,
        "--pipeline.llm-name",
        llm_name,
    ]
    if base_url:
        cmd_opt.extend(["--pipeline.base-url", base_url])
    cmd_opt.extend(
        [
            "route",  # ------------
            "--llm-name",
            llm_name,
            "--api-key",
            api_key,
        ]
    )
    if base_url:
        cmd_opt.extend(["--base-url", base_url])
    cmd_opt.extend(
        [
            "--pipeline-id",
            pipeline_id,
            "--prompt-set-id",
            prompt_set,
        ]
    )

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
        ]
    )
    if base_url:
        cmd_opt.extend(["--base-url", base_url])
    cmd_opt.extend(
        [
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
    base_url: Optional[str] = None,
    **_: Any,
):
    cmd_opt = [
        "--pipeline.pipeline-id",
        pipeline_id,
        "--pipeline.llm-name",
        llm_name,
    ]
    if base_url:
        cmd_opt.extend(["--pipeline.base-url", base_url])
    cmd_opt.extend(
        [
            "react",  # ------------
            "--llm-name",
            llm_name,
            "--api-key",
            api_key,
        ]
    )
    if base_url:
        cmd_opt.extend(["--base-url", base_url])
    cmd_opt.extend(
        [
            "--pipeline-id",
            pipeline_id,
            "--prompt-set-id",
            prompt_set,
        ]
    )
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
    base_url: Optional[str] = None,
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
    ]
    if base_url:
        cmd_opt.extend(["--pipeline.base-url", base_url])
    cmd_opt.extend(
        [
            "deepagent",
            "--llm-name",
            llm_name,
            "--api-key",
            api_key,
        ]
    )
    if base_url:
        cmd_opt.extend(["--base-url", base_url])
    cmd_opt.extend(
        [
            "--pipeline-id",
            pipeline_id,
            "--prompt-set-id",
            prompt_set,
        ]
    )

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
    base_url: Optional[str] = None,
    **_: Any,
):
    cmd_opt = [
        "--pipeline.pipeline-id",
        pipeline_id,
        "--pipeline.llm-name",
        llm_name,
    ]
    if base_url:
        cmd_opt.extend(["--pipeline.base-url", base_url])
    cmd_opt.extend(
        [
            "hybrid_rag",  # ------------
            "--llm-name",
            llm_name,
            "--api-key",
            api_key,
        ]
    )
    if base_url:
        cmd_opt.extend(["--base-url", base_url])
    cmd_opt.extend(["--pipeline-id", pipeline_id])
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

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import glob
import os
import os.path as osp
import sys
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import commentjson
import psycopg


PROJECT_ROOT = osp.dirname(osp.dirname(osp.dirname(osp.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from lang_agent.config import load_tyro_conf  # noqa: E402
from lang_agent.config.db_config_manager import DBConfigManager  # noqa: E402


@dataclass
class MigrationPayload:
    config_path: str
    pipeline_id: str
    graph_id: str
    prompt_dict: Dict[str, str]
    tool_keys: List[str]
    api_key: Optional[str]


def _infer_pipeline_id(pipeline_conf, config_path: str) -> str:
    candidates = [
        getattr(pipeline_conf, "pipeline_id", None),
        getattr(getattr(pipeline_conf, "graph_config", None), "pipeline_id", None),
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        value = str(candidate).strip()
        if value and value.lower() != "null":
            return value
    return osp.splitext(osp.basename(config_path))[0]


def _infer_graph_id(graph_conf) -> str:
    if graph_conf is None:
        return "unknown"
    class_name = graph_conf.__class__.__name__.lower()
    if "routing" in class_name or class_name == "routeconfig":
        return "routing"
    if "react" in class_name:
        return "react"

    target = getattr(graph_conf, "_target", None)
    if target is not None:
        target_name = getattr(target, "__name__", str(target)).lower()
        if "routing" in target_name:
            return "routing"
        if "react" in target_name:
            return "react"
    return "unknown"


def _extract_tool_keys(graph_conf) -> List[str]:
    if graph_conf is None:
        return []
    tool_cfg = getattr(graph_conf, "tool_manager_config", None)
    client_cfg = getattr(tool_cfg, "client_tool_manager", None)
    keys = getattr(client_cfg, "tool_keys", None)
    if not keys:
        return []
    out: List[str] = []
    seen = set()
    for key in keys:
        cleaned = str(key).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def _load_prompt_dict(prompt_path: str, default_key: str = "sys_prompt") -> Dict[str, str]:
    if not prompt_path:
        return {}
    if not osp.exists(prompt_path):
        return {}

    if osp.isdir(prompt_path):
        prompt_files = sorted(
            p for p in glob.glob(osp.join(prompt_path, "*.txt")) if "optional" not in p
        )
        out = {}
        for prompt_f in prompt_files:
            key = osp.splitext(osp.basename(prompt_f))[0]
            with open(prompt_f, "r", encoding="utf-8") as f:
                out[key] = f.read()
        return out

    if prompt_path.endswith(".json"):
        with open(prompt_path, "r", encoding="utf-8") as f:
            obj = commentjson.load(f)
        if not isinstance(obj, dict):
            return {}
        return {str(k): v if isinstance(v, str) else str(v) for k, v in obj.items()}

    if prompt_path.endswith(".txt"):
        with open(prompt_path, "r", encoding="utf-8") as f:
            return {default_key: f.read()}

    return {}


def _extract_prompt_dict(graph_conf) -> Dict[str, str]:
    if graph_conf is None:
        return {}
    if hasattr(graph_conf, "sys_prompt_f"):
        return _load_prompt_dict(str(getattr(graph_conf, "sys_prompt_f")), "sys_prompt")
    if hasattr(graph_conf, "sys_promp_dir"):
        return _load_prompt_dict(str(getattr(graph_conf, "sys_promp_dir")))
    return {}


def _extract_tool_node_prompt_dict(graph_conf) -> Dict[str, str]:
    tool_node_conf = getattr(graph_conf, "tool_node_config", None)
    if tool_node_conf is None:
        return {}

    out: Dict[str, str] = {}
    if hasattr(tool_node_conf, "tool_prompt_f"):
        out.update(
            _load_prompt_dict(str(getattr(tool_node_conf, "tool_prompt_f")), "tool_prompt")
        )
    if hasattr(tool_node_conf, "chatty_sys_prompt_f"):
        out.update(
            _load_prompt_dict(
                str(getattr(tool_node_conf, "chatty_sys_prompt_f")), "chatty_prompt"
            )
        )
    return out


def _prompt_key_whitelist(graph_conf, graph_id: str) -> Optional[set]:
    if graph_id == "react":
        return {"sys_prompt"}
    if graph_id != "routing":
        return None

    allowed = {"route_prompt", "chat_prompt", "tool_prompt"}
    tool_node_conf = getattr(graph_conf, "tool_node_config", None)
    if tool_node_conf is None:
        return allowed

    cls_name = tool_node_conf.__class__.__name__.lower()
    target = getattr(tool_node_conf, "_target", None)
    target_name = getattr(target, "__name__", str(target)).lower() if target else ""
    if "chatty" in cls_name or "chatty" in target_name:
        allowed.add("chatty_prompt")
    return allowed


def _collect_payload(config_path: str) -> MigrationPayload:
    conf = load_tyro_conf(config_path)
    graph_conf = getattr(conf, "graph_config", None)
    graph_id = _infer_graph_id(graph_conf)
    prompt_dict = _extract_prompt_dict(graph_conf)
    prompt_dict.update(_extract_tool_node_prompt_dict(graph_conf))
    whitelist = _prompt_key_whitelist(graph_conf, graph_id)
    if whitelist is not None:
        prompt_dict = {k: v for k, v in prompt_dict.items() if k in whitelist}
    return MigrationPayload(
        config_path=config_path,
        pipeline_id=_infer_pipeline_id(conf, config_path),
        graph_id=graph_id,
        prompt_dict=prompt_dict,
        tool_keys=_extract_tool_keys(graph_conf),
        api_key=getattr(conf, "api_key", None),
    )


def _resolve_config_paths(config_dir: str, config_paths: Optional[Iterable[str]]) -> List[str]:
    if config_paths:
        resolved = [osp.abspath(path) for path in config_paths]
    else:
        pattern = osp.join(osp.abspath(config_dir), "*.yaml")
        resolved = sorted(glob.glob(pattern))
    return [path for path in resolved if osp.exists(path)]


def _ensure_prompt_set(
    conn: psycopg.Connection,
    pipeline_id: str,
    graph_id: str,
    set_name: str,
    description: str,
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM prompt_sets
            WHERE pipeline_id = %s AND name = %s
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """,
            (pipeline_id, set_name),
        )
        row = cur.fetchone()
        if row is not None:
            return str(row[0])

        cur.execute(
            """
            INSERT INTO prompt_sets (pipeline_id, graph_id, name, description, is_active, list)
            VALUES (%s, %s, %s, %s, false, '')
            RETURNING id
            """,
            (pipeline_id, graph_id, set_name, description),
        )
        created = cur.fetchone()
        return str(created[0])


def _activate_prompt_set(conn: psycopg.Connection, pipeline_id: str, prompt_set_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE prompt_sets SET is_active = false, updated_at = now() WHERE pipeline_id = %s",
            (pipeline_id,),
        )
        cur.execute(
            "UPDATE prompt_sets SET is_active = true, updated_at = now() WHERE id = %s",
            (prompt_set_id,),
        )


def _run_migration(
    payloads: List[MigrationPayload],
    set_name: str,
    description: str,
    dry_run: bool,
    activate: bool,
) -> None:
    for payload in payloads:
        print(
            f"[PLAN] pipeline={payload.pipeline_id} graph={payload.graph_id} "
            f"prompts={len(payload.prompt_dict)} tools={len(payload.tool_keys)} "
            f"config={payload.config_path}"
        )
        if dry_run:
            continue

        manager = DBConfigManager()
        with psycopg.connect(manager.conn_str) as conn:
            prompt_set_id = _ensure_prompt_set(
                conn=conn,
                pipeline_id=payload.pipeline_id,
                graph_id=payload.graph_id,
                set_name=set_name,
                description=description,
            )
            conn.commit()

            manager.set_config(
                pipeline_id=payload.pipeline_id,
                graph_id=payload.graph_id,
                prompt_set_id=prompt_set_id,
                tool_list=payload.tool_keys,
                prompt_dict=payload.prompt_dict,
                api_key=payload.api_key,
            )

            if activate:
                _activate_prompt_set(
                    conn=conn,
                    pipeline_id=payload.pipeline_id,
                    prompt_set_id=prompt_set_id,
                )
                conn.commit()

        print(
            f"[DONE] pipeline={payload.pipeline_id} "
            f"prompt_set={prompt_set_id} activate={activate}"
        )


def main() -> None:
    date_str = dt.date.today().isoformat()
    parser = argparse.ArgumentParser(
        description="Import prompt definitions from pipeline YAML files into DB prompt_sets."
    )
    parser.add_argument(
        "--config-dir",
        default=osp.join(PROJECT_ROOT, "configs", "pipelines"),
        help="Directory containing pipeline YAML files.",
    )
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        help="Specific pipeline config yaml path. Can be passed multiple times.",
    )
    parser.add_argument(
        "--pipeline-id",
        action="append",
        default=[],
        help="If provided, only migrate these pipeline IDs (repeatable).",
    )
    parser.add_argument(
        "--set-name",
        # default=f"migrated-{date_str}",
        default="default",
        help="Prompt set name to create/reuse under each pipeline.",
    )
    parser.add_argument(
        "--description",
        default="Migrated from pipeline YAML prompt files",
        help="Prompt set description.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be migrated without writing to DB.",
    )
    parser.add_argument(
        "--activate",
        action="store_true",
        help="Mark imported set active for each migrated pipeline.",
    )
    args = parser.parse_args()

    config_paths = _resolve_config_paths(args.config_dir, args.config)
    if not config_paths:
        raise SystemExit("No config files found. Provide --config or --config-dir.")

    requested_pipelines = {p.strip() for p in args.pipeline_id if p.strip()}

    payloads: List[MigrationPayload] = []
    for config_path in config_paths:
        payload = _collect_payload(config_path)
        if requested_pipelines and payload.pipeline_id not in requested_pipelines:
            continue
        if not payload.prompt_dict:
            print(f"[SKIP] no prompts found for config={config_path}")
            continue
        payloads.append(payload)

    if not payloads:
        raise SystemExit("No pipelines matched with prompt content to migrate.")

    _run_migration(
        payloads=payloads,
        set_name=args.set_name,
        description=args.description,
        dry_run=args.dry_run,
        activate=args.activate,
    )


if __name__ == "__main__":
    main()


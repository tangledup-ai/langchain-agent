from fastapi import HTTPException
from typing import Any, Dict, Optional, Tuple
from pathlib import Path as FsPath
import os.path as osp
import json
import copy
from loguru import logger

from lang_agent.pipeline import Pipeline, PipelineConfig
from lang_agent.config.core_config import load_tyro_conf


class ServerPipelineManager:
    """Lazily load and cache multiple pipelines keyed by a client-facing route id."""

    def __init__(self, default_route_id: str, default_config: PipelineConfig):
        self.default_route_id = default_route_id
        self.default_config = default_config
        self._route_specs: Dict[str, Dict[str, Any]] = {}
        self._api_key_policy: Dict[str, Dict[str, Any]] = {}
        self._pipelines: Dict[str, Pipeline] = {}
        self._pipeline_llm: Dict[str, str] = {}

    def _resolve_registry_path(self, registry_path: str) -> str:
        path = FsPath(registry_path)
        if path.is_absolute():
            return str(path)
        # server_pipeline_manager.py is under <repo>/lang_agent/components/,
        # so parents[2] is the repository root.
        root = FsPath(__file__).resolve().parents[2]
        return str((root / path).resolve())

    def load_registry(self, registry_path: str) -> None:
        abs_path = self._resolve_registry_path(registry_path)
        if not osp.exists(abs_path):
            raise ValueError(f"pipeline registry file not found: {abs_path}")

        with open(abs_path, "r", encoding="utf-8") as f:
            registry:dict = json.load(f)

        routes = registry.get("routes")
        if routes is None:
            # Backward compatibility with initial schema.
            routes = registry.get("pipelines", {})
        if not isinstance(routes, dict):
            raise ValueError("`routes` in pipeline registry must be an object.")

        self._route_specs = {}
        for route_id, spec in routes.items():
            if not isinstance(spec, dict):
                raise ValueError(f"route spec for `{route_id}` must be an object.")
            self._route_specs[route_id] = {
                "enabled": bool(spec.get("enabled", True)),
                "config_file": spec.get("config_file"),
                "overrides": spec.get("overrides", {}),
                # Explicitly separates routing id from prompt config pipeline_id.
                "prompt_pipeline_id": spec.get("prompt_pipeline_id"),
            }
        if not self._route_specs:
            raise ValueError("pipeline registry must define at least one route.")

        api_key_policy = registry.get("api_keys", {})
        if api_key_policy and not isinstance(api_key_policy, dict):
            raise ValueError("`api_keys` in pipeline registry must be an object.")
        self._api_key_policy = api_key_policy
        logger.info(f"loaded pipeline registry: {abs_path}, routes={list(self._route_specs.keys())}")

    def _resolve_config_path(self, config_file: str) -> str:
        path = FsPath(config_file)
        if path.is_absolute():
            return str(path)
        # Resolve relative config paths from repository root for consistency
        # with docker-compose and tests.
        root = FsPath(__file__).resolve().parents[2]
        return str((root / path).resolve())

    def _build_pipeline(self, route_id: str) -> Tuple[Pipeline, str]:
        spec = self._route_specs.get(route_id)
        if spec is None:
            raise HTTPException(status_code=404, detail=f"Unknown route_id: {route_id}")
        if not spec.get("enabled", True):
            raise HTTPException(status_code=403, detail=f"Route disabled: {route_id}")

        config_file = spec.get("config_file")
        overrides = spec.get("overrides", {})
        if config_file:
            loaded_cfg = load_tyro_conf(self._resolve_config_path(config_file))
            # Some legacy yaml configs deserialize to plain dicts instead of
            # InstantiateConfig dataclasses. Fall back to default config in that case.
            if hasattr(loaded_cfg, "setup"):
                cfg = loaded_cfg
            else:
                logger.warning(
                    f"config_file for route `{route_id}` did not deserialize to config object; "
                    "falling back to default config and applying route-level overrides."
                )
                cfg = copy.deepcopy(self.default_config)
        else:
            # Build from default config + shallow overrides so new pipelines can be
            # added via registry without additional yaml files.
            cfg = copy.deepcopy(self.default_config)
        if not isinstance(overrides, dict):
            raise ValueError(f"route `overrides` for `{route_id}` must be an object.")
        for key, value in overrides.items():
            if not hasattr(cfg, key):
                raise ValueError(f"unknown override field `{key}` for route `{route_id}`")
            setattr(cfg, key, value)

        prompt_pipeline_id = spec.get("prompt_pipeline_id")
        if prompt_pipeline_id and (not isinstance(overrides, dict) or "pipeline_id" not in overrides):
            if hasattr(cfg, "pipeline_id"):
                cfg.pipeline_id = prompt_pipeline_id

        p = cfg.setup()
        llm_name = getattr(cfg, "llm_name", "unknown-model")
        return p, llm_name

    def _authorize(self, api_key: str, route_id: str) -> None:
        if not self._api_key_policy:
            return

        policy = self._api_key_policy.get(api_key)
        if policy is None:
            return

        allowed = policy.get("allowed_route_ids")
        if allowed is None:
            # Backward compatibility.
            allowed = policy.get("allowed_pipeline_ids")
        if allowed and route_id not in allowed:
            raise HTTPException(status_code=403, detail=f"route_id `{route_id}` is not allowed for this API key")

    def resolve_route_id(self, body: Dict[str, Any], app_id: Optional[str], api_key: str) -> str:
        body_input = body.get("input", {})
        route_id = (
            body.get("route_id")
            or (body_input.get("route_id") if isinstance(body_input, dict) else None)
            or body.get("pipeline_key")
            or (body_input.get("pipeline_key") if isinstance(body_input, dict) else None)
            # Backward compatibility: pipeline_id still accepted as route selector.
            or body.get("pipeline_id")
            or (body_input.get("pipeline_id") if isinstance(body_input, dict) else None)
            or app_id
        )

        if not route_id:
            key_policy = self._api_key_policy.get(api_key, {}) if self._api_key_policy else {}
            route_id = key_policy.get("default_route_id")
            if not route_id:
                # Backward compatibility.
                route_id = key_policy.get("default_pipeline_id", self.default_route_id)

        if route_id not in self._route_specs:
            raise HTTPException(status_code=404, detail=f"Unknown route_id: {route_id}")

        self._authorize(api_key, route_id)
        return route_id

    def get_pipeline(self, route_id: str) -> Tuple[Pipeline, str]:
        cached = self._pipelines.get(route_id)
        if cached is not None:
            return cached, self._pipeline_llm[route_id]

        pipeline_obj, llm_name = self._build_pipeline(route_id)
        self._pipelines[route_id] = pipeline_obj
        self._pipeline_llm[route_id] = llm_name
        logger.info(f"lazy-loaded route_id={route_id} model={llm_name}")
        return pipeline_obj, llm_name


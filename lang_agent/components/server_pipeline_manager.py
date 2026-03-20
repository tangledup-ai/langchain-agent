from fastapi import HTTPException
from typing import Any, Dict, Optional, Tuple
from pathlib import Path as FsPath
import os.path as osp
import json
import copy
from threading import RLock
from loguru import logger

from lang_agent.pipeline import Pipeline, PipelineConfig
from lang_agent.config.core_config import load_tyro_conf


class ServerPipelineManager:
    """Lazily load and cache multiple pipelines keyed by a client-facing pipeline id."""

    def __init__(self, default_pipeline_id: str, default_config: PipelineConfig):
        self.default_pipeline_id = default_pipeline_id
        self.default_config = default_config
        self._pipeline_specs: Dict[str, Dict[str, Any]] = {}
        self._api_key_policy: Dict[str, Dict[str, Any]] = {}
        self._pipelines: Dict[str, Pipeline] = {}
        self._pipeline_llm: Dict[str, str] = {}
        self._registry_path: Optional[str] = None
        self._registry_mtime_ns: Optional[int] = None
        self._lock = RLock()

    def _resolve_registry_path(self, registry_path: str) -> str:
        path = FsPath(registry_path)
        if path.is_absolute():
            return str(path)
        # server_pipeline_manager.py is under <repo>/lang_agent/components/,
        # so parents[2] is the repository root.
        root = FsPath(__file__).resolve().parents[2]
        return str((root / path).resolve())

    def _stat_registry_mtime_ns(self, abs_path: str) -> int:
        return FsPath(abs_path).stat().st_mtime_ns

    def _read_registry(self, abs_path: str) -> Dict[str, Any]:
        with open(abs_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _apply_registry(self, abs_path: str, registry: Dict[str, Any], mtime_ns: int) -> bool:
        pipelines = registry.get("pipelines")
        if pipelines is None or not isinstance(pipelines, dict):
            raise ValueError("`pipelines` in pipeline registry must be an object.")

        parsed_specs: Dict[str, Dict[str, Any]] = {}
        for pipeline_id, spec in pipelines.items():
            if not isinstance(spec, dict):
                raise ValueError(
                    f"pipeline spec for `{pipeline_id}` must be an object."
                )
            parsed_specs[pipeline_id] = {
                "enabled": bool(spec.get("enabled", True)),
                "config_file": spec.get("config_file"),
                "llm_name": spec.get("llm_name"),
            }
        if not parsed_specs:
            raise ValueError("pipeline registry must define at least one pipeline.")

        api_key_policy = registry.get("api_keys", {})
        if api_key_policy and not isinstance(api_key_policy, dict):
            raise ValueError("`api_keys` in pipeline registry must be an object.")

        with self._lock:
            old_specs = self._pipeline_specs
            old_policy = self._api_key_policy
            old_mtime = self._registry_mtime_ns

            removed = set(old_specs.keys()) - set(parsed_specs.keys())
            added = set(parsed_specs.keys()) - set(old_specs.keys())
            modified = {
                pipeline_id
                for pipeline_id in (set(old_specs.keys()) & set(parsed_specs.keys()))
                if old_specs[pipeline_id] != parsed_specs[pipeline_id]
            }
            changed = bool(added or removed or modified or old_policy != api_key_policy)

            # Drop stale cache entries for deleted/changed pipelines so future requests
            # lazily rebuild from the refreshed registry spec.
            for pipeline_id in (removed | modified):
                self._pipelines.pop(pipeline_id, None)
                self._pipeline_llm.pop(pipeline_id, None)

            self._pipeline_specs = parsed_specs
            self._api_key_policy = api_key_policy
            self._registry_path = abs_path
            self._registry_mtime_ns = mtime_ns

        if changed:
            logger.info(
                "refreshed pipeline registry: {} | added={} modified={} removed={} mtime={}",
                abs_path,
                sorted(added),
                sorted(modified),
                sorted(removed),
                mtime_ns,
            )
        elif old_mtime != mtime_ns:
            logger.debug("pipeline registry mtime changed but specs were unchanged: {}", abs_path)
        return changed

    def load_registry(self, registry_path: str) -> None:
        abs_path = self._resolve_registry_path(registry_path)
        if not osp.exists(abs_path):
            raise ValueError(f"pipeline registry file not found: {abs_path}")
        registry = self._read_registry(abs_path)
        mtime_ns = self._stat_registry_mtime_ns(abs_path)
        self._apply_registry(abs_path=abs_path, registry=registry, mtime_ns=mtime_ns)

    def refresh_registry_if_needed(
        self, registry_path: Optional[str] = None, force: bool = False
    ) -> bool:
        abs_path = (
            self._resolve_registry_path(registry_path)
            if registry_path
            else self._registry_path
        )
        if not abs_path:
            raise ValueError("registry path is not initialized")
        if not osp.exists(abs_path):
            raise ValueError(f"pipeline registry file not found: {abs_path}")

        mtime_ns = self._stat_registry_mtime_ns(abs_path)
        with self._lock:
            if not force and self._registry_mtime_ns == mtime_ns:
                return False

        registry = self._read_registry(abs_path)
        return self._apply_registry(abs_path=abs_path, registry=registry, mtime_ns=mtime_ns)

    def _resolve_config_path(self, config_file: str) -> str:
        path = FsPath(config_file)
        if path.is_absolute():
            return str(path)
        # Resolve relative config paths from repository root for consistency
        # with docker-compose and tests.
        root = FsPath(__file__).resolve().parents[2]
        return str((root / path).resolve())

    def _build_pipeline(self, pipeline_id: str) -> Tuple[Pipeline, str]:
        spec = self._pipeline_specs.get(pipeline_id)
        if spec is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown pipeline_id: {pipeline_id}"
            )
        if not spec.get("enabled", True):
            raise HTTPException(
                status_code=403, detail=f"Pipeline disabled: {pipeline_id}"
            )

        config_file = spec.get("config_file")
        registry_llm_name = spec.get("llm_name")
        if config_file:
            loaded_cfg = load_tyro_conf(self._resolve_config_path(config_file))
            if hasattr(loaded_cfg, "setup"):
                cfg = loaded_cfg
            else:
                logger.warning(
                    "config_file for pipeline `{}` did not deserialize to a config object; "
                    "falling back to default pipeline config",
                    pipeline_id,
                )
                cfg = copy.deepcopy(self.default_config)
                if registry_llm_name is not None and hasattr(cfg, "llm_name"):
                    setattr(cfg, "llm_name", registry_llm_name)
        else:
            cfg = copy.deepcopy(self.default_config)
            if registry_llm_name is not None and hasattr(cfg, "llm_name"):
                setattr(cfg, "llm_name", registry_llm_name)

        p = cfg.setup()
        llm_name = str(getattr(cfg, "llm_name", registry_llm_name or "unknown-model"))
        return p, llm_name

    def _authorize(self, api_key: str, pipeline_id: str) -> None:
        if not self._api_key_policy:
            return

        policy = self._api_key_policy.get(api_key)
        if policy is None:
            return

        allowed = policy.get("allowed_pipeline_ids")
        if allowed and pipeline_id not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"pipeline_id `{pipeline_id}` is not allowed for this API key",
            )

    def resolve_pipeline_id(
        self, body: Dict[str, Any], app_id: Optional[str], api_key: str
    ) -> str:
        body_input = body.get("input", {})
        pipeline_id = (
            body.get("pipeline_id")
            or (body_input.get("pipeline_id") if isinstance(body_input, dict) else None)
            or app_id
        )

        with self._lock:
            if not pipeline_id:
                key_policy = (
                    self._api_key_policy.get(api_key, {}) if self._api_key_policy else {}
                )
                pipeline_id = key_policy.get(
                    "default_pipeline_id", self.default_pipeline_id
                )

            if pipeline_id not in self._pipeline_specs:
                raise HTTPException(
                    status_code=404, detail=f"Unknown pipeline_id: {pipeline_id}"
                )

            self._authorize(api_key, pipeline_id)
        return pipeline_id

    def get_pipeline(self, pipeline_id: str) -> Tuple[Pipeline, str]:
        with self._lock:
            cached = self._pipelines.get(pipeline_id)
            if cached is not None:
                return cached, self._pipeline_llm[pipeline_id]

            # Build while holding the lock to avoid duplicate construction for
            # the same pipeline on concurrent first requests.
            pipeline_obj, llm_name = self._build_pipeline(pipeline_id)
            self._pipelines[pipeline_id] = pipeline_obj
            self._pipeline_llm[pipeline_id] = llm_name
        logger.info(f"lazy-loaded pipeline_id={pipeline_id} model={llm_name}")
        return pipeline_obj, llm_name

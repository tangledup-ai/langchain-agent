from typing import Dict, Optional
from abc import ABC, abstractmethod
import os
import os.path as osp
import glob
import commentjson
import psycopg
from loguru import logger


class PromptStoreBase(ABC):
    """Interface for getting prompts by key."""

    @abstractmethod
    def get(self, key: str) -> str:
        """Get a prompt by key. Raises KeyError if not found."""
        ...

    @abstractmethod
    def get_all(self) -> Dict[str, str]:
        """Get all available prompts as {key: content}."""
        ...

    def __contains__(self, key: str) -> bool:
        try:
            self.get(key)
            return True
        except KeyError:
            return False


class FilePromptStore(PromptStoreBase):
    """
    Loads prompts from files — preserves existing behavior exactly.

    Supports:
      - A directory of .txt files (key = filename without extension)
      - A single .json file (keys from JSON object)
      - A single .txt file (stored under a provided default_key)
    """

    def __init__(self, path: str, default_key: str = "sys_prompt"):
        self._prompts: Dict[str, str] = {}
        self._load(path, default_key)

    def _load(self, path: str, default_key: str):
        if not path or not osp.exists(path):
            logger.warning(f"Prompt path does not exist: {path}")
            return

        if osp.isdir(path):
            # Directory of .txt files — same as RoutingGraph._load_sys_prompts()
            sys_fs = glob.glob(osp.join(path, "*.txt"))
            sys_fs = sorted([e for e in sys_fs if "optional" not in e])
            for sys_f in sys_fs:
                key = osp.basename(sys_f).split(".")[0]
                with open(sys_f, "r") as f:
                    self._prompts[key] = f.read()

        elif path.endswith(".json"):
            # JSON file — same as RoutingGraph._load_sys_prompts()
            with open(path, "r") as f:
                self._prompts = commentjson.load(f)

        elif path.endswith(".txt"):
            # Single text file — same as ReactGraph / ToolNode
            with open(path, "r") as f:
                self._prompts[default_key] = f.read()
        else:
            raise ValueError(f"Unsupported prompt path format: {path}")

        for k in self._prompts:
            logger.info(f"FilePromptStore loaded: '{k}'")

    def get(self, key: str) -> str:
        if key not in self._prompts:
            raise KeyError(f"Prompt '{key}' not found in file store")
        return self._prompts[key]

    def get_all(self) -> Dict[str, str]:
        return dict(self._prompts)


class DBPromptStore(PromptStoreBase):
    """
    Loads prompts from PostgreSQL via prompt_sets + prompt_templates tables.

    Schema:
        prompt_sets    (id, pipeline_id, name, is_active, ...)
        prompt_templates (id, prompt_set_id FK, prompt_key, content, ...)

    By default loads from the active prompt set for the given pipeline_id.
    A specific prompt_set_id can be provided to target a non-active set
    (useful for previewing or A/B testing).
    """

    def __init__(
        self,
        pipeline_id: str,
        prompt_set_id: str = None,
        conn_str: str = None,
    ):
        self.pipeline_id = pipeline_id
        self.prompt_set_id = prompt_set_id
        self.conn_str = conn_str or os.environ.get("CONN_STR")
        if not self.conn_str:
            raise ValueError("CONN_STR not set for DBPromptStore")
        self._cache: Optional[Dict[str, str]] = None  # lazy loaded

    def _load(self):
        """Load all prompts for the active (or specified) prompt set from DB."""
        if self._cache is not None:
            return
        self._cache = {}
        try:
            with psycopg.connect(self.conn_str) as conn:
                with conn.cursor() as cur:
                    if self.prompt_set_id:
                        # Load from a specific prompt set
                        cur.execute(
                            "SELECT prompt_key, content FROM prompt_templates "
                            "WHERE prompt_set_id = %s",
                            (self.prompt_set_id,),
                        )
                    else:
                        # Load from the active prompt set for this pipeline
                        cur.execute(
                            "SELECT pt.prompt_key, pt.content "
                            "FROM prompt_templates pt "
                            "JOIN prompt_sets ps ON pt.prompt_set_id = ps.id "
                            "WHERE ps.pipeline_id = %s AND ps.is_active = true",
                            (self.pipeline_id,),
                        )
                    for row in cur.fetchall():
                        self._cache[row[0]] = row[1]
            source = f"set '{self.prompt_set_id}'" if self.prompt_set_id else "active set"
            logger.info(
                f"DBPromptStore loaded {len(self._cache)} prompts for pipeline "
                f"'{self.pipeline_id}' ({source})"
            )
        except Exception as e:
            logger.warning(f"DBPromptStore failed to load: {e}")
            self._cache = {}

    def invalidate_cache(self):
        """Force reload on next access (call after prompt update via API)."""
        self._cache = None

    def get(self, key: str) -> str:
        self._load()
        if key not in self._cache:
            raise KeyError(
                f"Prompt '{key}' not in DB for pipeline '{self.pipeline_id}'"
            )
        return self._cache[key]

    def get_all(self) -> Dict[str, str]:
        self._load()
        return dict(self._cache)


class FallbackPromptStore(PromptStoreBase):
    """
    Tries primary store (DB) first, falls back to secondary (files).
    This is the main store graphs should use.
    """

    def __init__(self, primary: PromptStoreBase, fallback: PromptStoreBase):
        self.primary = primary
        self.fallback = fallback

    def get(self, key: str) -> str:
        try:
            val = self.primary.get(key)
            logger.debug(f"Prompt '{key}' resolved from primary store")
            return val
        except KeyError:
            logger.debug(f"Prompt '{key}' not in primary, trying fallback")
            return self.fallback.get(key)

    def get_all(self) -> Dict[str, str]:
        merged = self.fallback.get_all()
        merged.update(self.primary.get_all())  # primary overrides fallback
        return merged


class HardcodedPromptStore(PromptStoreBase):
    """For graphs that currently use module-level constants."""

    def __init__(self, prompts: Dict[str, str]):
        self._prompts = prompts

    def get(self, key: str) -> str:
        if key not in self._prompts:
            raise KeyError(f"Prompt '{key}' not in hardcoded store")
        return self._prompts[key]

    def get_all(self) -> Dict[str, str]:
        return dict(self._prompts)


def build_prompt_store(
    pipeline_id: Optional[str] = None,
    prompt_set_id: Optional[str] = None,
    file_path: Optional[str] = None,
    default_key: str = "sys_prompt",
    hardcoded: Optional[Dict[str, str]] = None,
) -> PromptStoreBase:
    """
    Factory function — builds the right prompt store based on what's provided.

    Priority: DB (if pipeline_id) > Files (if file_path) > Hardcoded

    When pipeline_id is None (default), DB layer is skipped entirely and
    existing file-based / hardcoded behavior is preserved.

    Args:
        pipeline_id:   Loads from the active prompt_set for this pipeline.
        prompt_set_id: If provided, loads from this specific prompt set
                       instead of the active one (useful for preview / A/B).
        file_path:     Path to file or directory for file-based fallback.
        default_key:   Key name when file_path points to a single .txt file.
        hardcoded:     Dict of prompt_key → content as last-resort defaults.
    """
    stores = []

    if prompt_set_id:
        try:
            stores.append(DBPromptStore(pipeline_id, prompt_set_id=prompt_set_id))
        except ValueError:
            logger.warning("CONN_STR not set, skipping DB prompt store")

    if file_path and osp.exists(file_path):
        stores.append(FilePromptStore(file_path, default_key))

    if hardcoded:
        stores.append(HardcodedPromptStore(hardcoded))

    if not stores:
        raise ValueError("No prompt source available")

    # Chain them: first store is highest priority
    result = stores[-1]
    for store in reversed(stores[:-1]):
        result = FallbackPromptStore(primary=store, fallback=result)

    return result


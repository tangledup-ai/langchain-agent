import os
import re
import os.path as osp
from fastapi.security import APIKeyHeader

_PROJECT_ROOT = osp.dirname(osp.dirname(osp.dirname(osp.abspath(__file__))))

MCP_CONFIG_PATH = osp.join(_PROJECT_ROOT, "configs", "mcp_config.json")
MCP_CONFIG_DEFAULT_CONTENT = "{\n}\n"
PIPELINE_REGISTRY_PATH = osp.join(_PROJECT_ROOT, "configs", "pipeline_registry.json")

API_KEY_HEADER = APIKeyHeader(name="Authorization", auto_error=True)
API_KEY_HEADER_NO_ERROR = APIKeyHeader(name="Authorization", auto_error=False)

VALID_API_KEYS = set(filter(None, os.environ.get("FAST_AUTH_KEYS", "").split(",")))

#!/usr/bin/env python3
"""
Register all pipeline YAML configs in configs/pipelines/ to the registry.

This is a one-time setup script that should be run during installation.
It scans configs/pipelines/*.yaml, extracts metadata, and populates
configs/pipeline_registry.json.

Usage:
    python scripts/py_scripts/register_pipelines.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lang_agent.front_api.build_server_utils import sync_pipeline_registry_from_configs
from lang_agent.config.constants import PIPELINE_REGISTRY_PATH


def main():
    print("Registering pipelines from configs/pipelines/...")
    
    changed = sync_pipeline_registry_from_configs(registry_f=PIPELINE_REGISTRY_PATH)
    
    if changed:
        print(f"✓ Updated {PIPELINE_REGISTRY_PATH}")
        print("  New or modified pipelines have been registered.")
    else:
        print(f"✓ Registry is up to date ({PIPELINE_REGISTRY_PATH})")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

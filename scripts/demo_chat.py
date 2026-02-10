import tyro
from typing import Annotated
import uuid
from loguru import logger

from lang_agent.pipeline import Pipeline, PipelineConfig
from lang_agent.config import load_tyro_conf
from lang_agent.components.conv_store import use_printer

import os
import re
from typing import Dict, List, Tuple

def fix_proxy_env_vars(
    dry_run: bool = False,
    verbose: bool = True
) -> Tuple[Dict[str, Tuple[str, str]], Dict[str, str]]:
    """
    Auto-fix proxy environment variables in-place.
    
    Fixes invalid schemes:
      - socks://   → socks5://
      - socks5://  → socks5:// (unchanged)
      - socks4://  → socks4:// (unchanged)
      - http://    → http://   (unchanged)
      - https://   → https://  (unchanged)
    
    Args:
        dry_run: If True, only report changes without modifying env vars.
        verbose: If True, print changes to stdout.
    
    Returns:
        Tuple of:
          - Dict of {var_name: (old_value, new_value)} for changed vars
          - Dict of current proxy env vars after fix
    """
    proxy_vars = [
        "HTTP_PROXY", "http_proxy",
        "HTTPS_PROXY", "https_proxy",
        "ALL_PROXY", "all_proxy"
    ]
    
    scheme_fixes = [
        (re.compile(r'^socks5?://', re.IGNORECASE), 'socks5://'),  # socks:// or socks5:// → socks5://
        (re.compile(r'^socks4a?://', re.IGNORECASE), 'socks4://'), # socks4:// or socks4a:// → socks4://
    ]
    
    changed = {}
    current_proxies = {}
    
    for var in proxy_vars:
        value = os.environ.get(var)
        if not value:
            continue
        
        current_proxies[var] = value
        new_value = value
        
        # Apply scheme fixes
        for pattern, replacement in scheme_fixes:
            if pattern.match(value):
                new_value = replacement + value[pattern.match(value).end():]
                break
        
        # Only update if value actually changed
        if new_value != value:
            changed[var] = (value, new_value)
            if not dry_run:
                os.environ[var] = new_value
                current_proxies[var] = new_value
    
    # Report changes
    if verbose:
        if changed:
            action = "Would fix" if dry_run else "Fixed"
            print(f"✅ {action} proxy environment variables:")
            for var, (old, new) in changed.items():
                print(f"   {var}: {old} → {new}")
        else:
            print("✅ No proxy environment variables need fixing.")
        
        if current_proxies and not dry_run:
            print("\n🔧 Current proxy settings:")
            for var in sorted(set(k.upper() for k in current_proxies)):
                val = os.environ.get(var, os.environ.get(var.lower(), ""))
                if val:
                    print(f"   {var}: {val}")
    
    return changed, current_proxies



def main(
    conf: PipelineConfig,
    stream: Annotated[bool, tyro.conf.arg(name="stream")] = True,
):
    """Demo chat script for langchain-agent pipeline.
    
    Args:
        conf: Pipeline configuration
        stream: Enable streaming mode for chat responses
    """
    fix_proxy_env_vars()
    use_printer()
    if conf.config_f is not None:
        conf = load_tyro_conf(conf.config_f)
    
    logger.info(conf)
    pipeline: Pipeline = conf.setup()
    thread_id = str(uuid.uuid4())
    while True:
        user_input = input("请讲：")
        if user_input.lower() == "exit":
            break
        
        if stream:
            # Streaming mode: print chunks as they arrive
            print("回答: ", end="", flush=True)
            for chunk in pipeline.chat(user_input, as_stream=True, thread_id=thread_id):
                print(chunk, end="", flush=True)
            print()  # New line after streaming completes
        else:
            # Non-streaming mode: print full response
            response = pipeline.chat(user_input, as_stream=False, thread_id=thread_id)
            print(f"回答: {response}")


if __name__ == "__main__":
    tyro.cli(main)
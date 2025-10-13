import json
import subprocess
import asyncio
import aiohttp
from loguru import logger

async def start_mcps_simple(config):
    """Simple function to start MCPs from config dictionary"""
    processes = []
    
    for name, mcp_config in config.items():
        transport = mcp_config.get("transport", "").lower()
        
        if transport == "stdio":
            # Start stdio-based MCP
            try:
                command = mcp_config.get("command")
                args = mcp_config.get("args", [])
                cmd = [command] + args
                
                logger.info(f"Starting {name} with command: {' '.join(cmd)}")
                process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                processes.append((name, process))
                logger.info(f"Started {name} (PID: {process.pid})")
                
            except Exception as e:
                logger.error(f"Failed to start {name}: {e}")
        
        elif transport == "streamable_http":
            # Check HTTP-based MCP
            try:
                url = mcp_config.get("url")
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=5) as response:
                        if response.status == 200:
                            logger.info(f"HTTP MCP {name} is accessible at {url}")
                        else:
                            logger.warning(f"HTTP MCP {name} returned status {response.status}")
            except Exception as e:
                logger.error(f"Failed to connect to {name}: {e}")
    
    return processes

# Usage example
async def main_simple(config=None):
    if config is None:
        config = {
            "calculator": {
                "transport": "stdio",
                "command": "python",
                "args": ["lang_agent/calculator.py"],
            }
        }
    
    processes = await start_mcps_simple(config)
    
    print(f"Started {len(processes)} processes")
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Stopping processes...")
        for name, process in processes:
            process.terminate()
            logger.info(f"Stopped {name}")


def run_all_mcps(mcp_config_f="configs/mcp_config.json"):
    with open(mcp_config_f, "r") as f:
        config = json.load(f)
    
    asyncio.run(main_simple(config))

if __name__ == "__main__":
    run_all_mcps()
    # asyncio.run(main_simple())

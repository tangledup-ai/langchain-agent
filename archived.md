# Start all mcps to websocket
1. Source all env variable
2. run the below
```bash
python scripts/start_mcp_server.py

# update configs/ws_mcp_config.json with link from the command above
python scripts/ws_start_register_tools.py
```
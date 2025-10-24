# langchain-agent


# Install
1. Install `xiaoliang-catering` for carttool support; otherwise, comment out in `lang_agent/tool_manager.py`

# Environs
Need these:
```bash
export ALI_API_KEY=REDACTED
export ALI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export MCP_ENDPOINT=REDACTED
export LANGSMITH_API_KEY=REDACTED
```

```bash
# for developement
python -m pip install -e .

# for production
python -m pip install .
```

# Runables
all runnables are under scripts

# Start all mcps to websocket
1. Source all env variable
2. run the below
```bash
python scripts/start_mcp_server.py

# update configs/ws_mcp_config.json with link from the command above
python scripts/ws_start_register_tools.py
```
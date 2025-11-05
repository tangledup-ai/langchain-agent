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

# Install
need to install: `xiaoliang-catering `

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

# Eval Dataset Format
see `scripts/make_eval_dataset.py` for example. Specific meaning of each entry:
```json
[
    {
        "inputs": {"text": "用retrieve查询光予尘然后介绍"}, // model input; use list for conversation
        "outputs": {"answer": "光予尘茉莉绿茶为底",         // reference answer
                    "tool_use": ["retrieve"]}            // tool uses; assume model need to use all tools if more than 1 provided 
    }
]
```


# Configure for Xiaozhi
0. Start the `fastapi_server/server_dashscope.py` file
1. Make a new model entry in `xiaozhi` with AliBL as provider. 
2. Fill in the `base_url` entry. The other entries (`API_KEY`, `APP_ID`) can be garbage
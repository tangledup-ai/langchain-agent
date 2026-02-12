# Lang Agent Chat API

这是一个基于FastAPI的聊天API服务，使用OpenAI格式的请求来调用pipeline.invoke方法进行聊天。

## 安装依赖

```bash
# recommended to install as dev to easily modify the configs in ./config
python -m pip install -e .
```

## 环境变量

make a `.env` with:

```bash
ALI_API_KEY=<ALI API KEY>
ALI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
LANGSMITH_API_KEY=<LANG SMITH API KEY> # for testing only
```

### Hardware tools
update the link to xiaozhi server in `configs/mcp_config.json`

## Configure for Xiaozhi
0. Start the `fastapi_server/server_dashscope.py` file
1. Make a new model entry in `xiaozhi` with AliBL as provider. 
2. Fill in the `base_url` entry. The other entries (`API_KEY`, `APP_ID`) can be garbage
    - for local computer `base_url=http://127.0.0.1:8588/api/`
    - if inside docker, it needs to be `base_url=http://{computer_ip}:8588/api/`



## 运行服务

#### API key setup
`server_dashcop.py` and `server_openai.py` both require api key; generate one and set

```bash
FAST_AUTH_KEYS=API_KEY1,API_KEY2    # at least one
```
`FAST_AUTH_KEYS` will be used as the api-key for authentication when the api is requested.

```bash
# for easy debug; streams full message internally for visibility
python fastapi_server/fake_stream_server_dashscopy.py

# for live production; this is streaming
python fastapi_server/server_dashscope.py

# start server with chatty tool node; NOTE: streaming only!
python fastapi_server/server_dashscope.py route chatty_tool_node

# this supports openai-api; 
python fastapi_server/server_openai.py
```
see sample usage in `fastapi_server/test_dashscope_client.py` to see how to communicate with `fake_stream_server_dashscopy.py` or `server_dashscope.py` service

## Conversation Viewer

A web UI to visualize and browse conversations stored in the PostgreSQL database.

### Setup

1. Ensure your database is set up (see `scripts/init_user.sql` and `scripts/recreate_table.sql`)
2. Set the `CONN_STR` environment variable:
   ```bash
   export CONN_STR="postgresql://myapp_user:secure_password_123@localhost/ai_conversations"
   ```

### Running the Viewer

```bash
python fastapi_server/server_viewer.py
```

Then open your browser and navigate to:
```
http://localhost:8590
```

### Features

- **Left Sidebar**: Lists all conversations with message counts and last updated timestamps
- **Main View**: Displays messages in a chat-style interface
  - Human messages appear on the right (blue bubbles)
  - AI messages appear on the left (green bubbles)
  - Tool messages appear on the left (orange bubbles with border)

The viewer automatically loads all conversations from the `messages` table and allows you to browse through them interactively.  

### Openai API differences
For the python `openai` package it does not handle memory. Ours does, so each call remembers what happens previously. For managing memory, pass in a `thread_id` to manager the conversations
```python
from openai import OpenAI

client = OpenAI(
        base_url=BASE_URL,
        api_key="test-key"  # see put a key in .env and put it here; see above
    )

client.chat.completions.create(
            model="qwen-plus", 
            messages=messages,
            stream=True,
            extra_body={"thread_id":"2000"}  # pass in a thread id; must be string
        )
```



## Runnables
everything in scripts: 
- For sample usage see `scripts/demo_chat.py`.
- To evaluate the current default config `scripts/eval.py`
- To make a dataset for eval `scripts/make_eval_dataset.py`


## Registering MCP service
put the links in `configs/mcp_config.json`

## Modifying LLM prompts
Refer to model above when modifying the prompts.  
they are in `configs/route_sys_prompts`
- `chat_prompt.txt`: controls `chat_model_call`
- `route_prompt.txt`: controls `router_call`
- `tool_prompt.txt`: controls `tool_model_call`
- `chatty_prompt.txt`: controls how the model say random things when tool use is in progress. Ignore this for now as model architecture is not yet configurable

## Frontend (Conversation Viewer UI)

The React-based frontend for browsing conversations lives in the `frontend` directory.

### Install dependencies

```bash
cd frontend
npm install
```

### Start the `front_apis` server

The frontend talks to the `front_apis` FastAPI service, which by default listens on `http://127.0.0.1:8001`.

From the project root:

```bash
uvicorn fastapi_server.front_apis:app --reload --host 0.0.0.0 --port 8001
```

You can change the URL by setting `VITE_FRONT_API_BASE_URL` in `frontend/.env` (defaults to `http://127.0.0.1:8001`).

### Start the development server

```bash
cd frontend
npm run dev
```

By default, Vite will start the app on `http://localhost:5173` (or the next available port).

## Stress Test results
### Dashscope server summary

#### Non-Streaming

| Concurrency | Requests | Success % | Throughput (req/s) | Avg Latency (ms) | p95 (ms) | p99 (ms) |
|-----------:|---------:|----------:|-------------------:|-----------------:|---------:|---------:|
| 1          | 10       | 100.00%   | 0.77               | 1293.14          | 1460.48  | 1476.77  |
| 5          | 25       | 100.00%   | 2.74               | 1369.23          | 1827.11  | 3336.25  |
| 10         | 50       | 100.00%   | 6.72               | 1344.48          | 1964.75  | 2165.77  |
| 20         | 100      | 100.00%   | 10.90              | 1688.06          | 2226.49  | 2747.19  |
| 50         | 200      | 100.00%   | 11.75              | 3877.01          | 4855.45  | 5178.52  |

#### Streaming

| Concurrency | Requests | Success % | Throughput (req/s) | Avg Latency (ms) | p95 (ms) | p99 (ms) |
|-----------:|---------:|----------:|-------------------:|-----------------:|---------:|---------:|
| 1          | 10       | 100.00%   | 0.73               | 1374.08          | 1714.61  | 1715.82  |
| 10         | 50       | 100.00%   | 5.97               | 1560.63          | 1925.01  | 2084.21  |
| 20         | 100      | 100.00%   | 9.28               | 2012.03          | 2649.72  | 2934.84  |

Interpretation - Handling concurrently 20 conversations should be ok
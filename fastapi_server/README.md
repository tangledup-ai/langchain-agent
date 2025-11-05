# Lang Agent Chat API

这是一个基于FastAPI的聊天API服务，使用OpenAI格式的请求来调用pipeline.invoke方法进行聊天。

## 功能特点

- 兼容OpenAI API格式的聊天接口
- 支持多轮对话（通过thread_id）
- 使用qwen-flash模型
- 支持流式和非流式响应
- 提供健康检查接口

## 安装依赖

```bash
pip install -r requirements.txt
```

## 环境变量

确保设置以下环境变量：

```bash
export ALI_API_KEY="your_ali_api_key"
```

## 运行服务

### 方法1：使用启动脚本

```bash
./start_server.sh
```

### 方法2：直接运行Python文件

```bash
python server.py
```

服务将在 `http://localhost:8000` 启动。

## API接口

### 聊天完成接口

**端点**: `POST /v1/chat/completions`

**请求格式**:
```json
{
  "model": "qwen-flash",
  "messages": [
    {
      "role": "system",
      "content": "你是一个有用的助手。"
    },
    {
      "role": "user",
      "content": "你好，请介绍一下你自己。"
    }
  ],
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": false,
  "thread_id": 3
}
```

**响应格式**:
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1677652288,
  "model": "qwen-flash",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好！我是小盏，是半盏青年茶馆的智能助手..."
      },
      "finish_reason": "stop"
    }
  ]
}
```

### API信息接口

**端点**: `GET /`

返回API的基本信息。

### 健康检查接口

**端点**: `GET /health`

返回服务的健康状态。

## 使用示例

### 使用OpenAI Python客户端库

首先安装OpenAI库：

```bash
pip install openai
```

然后使用以下代码：

```python
from openai import OpenAI

# 设置API基础URL和API密钥（这里使用一个虚拟的密钥，因为我们没有实现认证）
client = OpenAI(
    api_key="your-api-key",  # 这里可以使用任意值，因为我们的API没有实现认证
    base_url="http://localhost:8000/v1"
)

# 发送聊天请求
response = client.chat.completions.create(
    model="qwen-flash",
    messages=[
        {"role": "system", "content": "你是一个有用的助手。"},
        {"role": "user", "content": "你好，请介绍一下你自己。"}
    ],
    temperature=0.7,
    thread_id=1  # 用于多轮对话
)

print(response.choices[0].message.content)
```

### 使用curl

```bash
curl -X POST "http://localhost:8000/v1/chat/completions" \
-H "Content-Type: application/json" \
-d '{
  "model": "qwen-flash",
  "messages": [
    {
      "role": "user",
      "content": "你好，请介绍一下你自己。"
    }
  ]
}'
```

### 使用Python requests

```python
import requests

url = "http://localhost:8000/v1/chat/completions"
headers = {"Content-Type": "application/json"}
data = {
    "model": "qwen-flash",
    "messages": [
        {
            "role": "user",
            "content": "你好，请介绍一下你自己。"
        }
    ]
}

response = requests.post(url, headers=headers, json=data)
print(response.json())
```

## 注意事项

1. 确保已设置正确的API密钥环境变量
2. 默认使用qwen-flash模型，可以通过修改代码中的配置来更改模型
3. thread_id用于多轮对话，相同的thread_id会保持对话上下文
4. 目前stream参数设置为true时，仍会返回非流式响应（可根据需要进一步实现）
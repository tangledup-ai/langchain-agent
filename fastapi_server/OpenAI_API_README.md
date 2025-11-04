# Lang Agent OpenAI 兼容API

这是一个符合OpenAI接口规范的聊天API，允许用户使用与OpenAI API相同的方式访问您的Lang Agent服务。

## 快速开始

### 1. 启动服务器

```bash
cd /path/to/lang-agent/fastapi_server
python server.py
```

服务器将在 `http://localhost:8488` 上启动。

### 2. 使用API

#### 使用curl命令

```bash
curl -X POST "http://localhost:8488/v1/chat/completions" \
  -H "Authorization: Bearer 123tangledup-ai" \
  -H "Content-Type: application/json" \
  -d '{
      "model": "qwen-plus",
      "messages": [
          {
              "role": "system",
              "content": "You are a helpful assistant."
          },
          {
              "role": "user",
              "content": "你是谁？"
          }
      ]
  }'
```

#### 使用Python requests

```python
import requests

API_BASE_URL = "http://localhost:8488"
API_KEY = "123tangledup-ai"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

data = {
    "model": "qwen-plus",
    "messages": [
        {
            "role": "system",
            "content": "You are a helpful assistant."
        },
        {
            "role": "user",
            "content": "你是谁？"
        }
    ]
}

response = requests.post(f"{API_BASE_URL}/v1/chat/completions", headers=headers, json=data)
print(response.json())
```

#### 使用OpenAI Python库

```python
from openai import OpenAI

client = OpenAI(
    api_key="123tangledup-ai",
    base_url="http://localhost:8488/v1"
)

response = client.chat.completions.create(
    model="qwen-plus",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "你是谁？"}
    ]
)

print(response.choices[0].message.content)
```

## API 端点

### 1. 聊天完成 `/v1/chat/completions`

与OpenAI的chat completions API完全兼容。

**请求参数:**

| 参数 | 类型 | 必需 | 默认值 | 描述 |
|------|------|------|--------|------|
| model | string | 是 | - | 模型名称 |
| messages | array | 是 | - | 消息列表 |
| temperature | number | 否 | 0.7 | 采样温度 |
| max_tokens | integer | 否 | 500 | 最大生成token数 |
| stream | boolean | 否 | false | 是否流式返回 |
| thread_id | integer | 否 | 3 | 线程ID，用于多轮对话 |

**响应格式:**

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1677652288,
  "model": "qwen-plus",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "您好！我是一个AI助手..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 56,
    "completion_tokens": 31,
    "total_tokens": 87
  }
}
```

### 2. 健康检查 `/health`

检查API服务状态。

**请求:**
```bash
GET /health
```

**响应:**
```json
{
  "status": "healthy"
}
```

### 3. API信息 `/`

获取API基本信息。

**请求:**
```bash
GET /
```

**响应:**
```json
{
  "message": "Lang Agent Chat API",
  "version": "1.0.0",
  "description": "使用OpenAI格式调用pipeline.invoke的聊天API",
  "authentication": "Bearer Token (API Key)",
  "endpoints": {
    "/v1/chat/completions": "POST - 聊天完成接口，兼容OpenAI格式，需要API密钥验证",
    "/": "GET - API信息",
    "/health": "GET - 健康检查接口"
  }
}
```

## 认证

API使用Bearer Token认证。默认API密钥为 `123tangledup-ai`。

在请求头中包含：
```
Authorization: Bearer 123tangledup-ai
```

## 测试脚本

项目提供了两个测试脚本：

1. **Bash脚本** (`test_openai_api.sh`) - 使用curl命令测试API
2. **Python脚本** (`test_openai_api.py`) - 使用Python requests库测试API

运行测试脚本：

```bash
# 运行Bash测试脚本
chmod +x test_openai_api.sh
./test_openai_api.sh

# 运行Python测试脚本
python test_openai_api.py
```

## 与OpenAI API的兼容性

此API完全兼容OpenAI的chat completions API，您可以：

1. 使用任何支持OpenAI API的客户端库
2. 将base_url更改为`http://localhost:8488/v1`
3. 使用提供的API密钥进行认证

## 注意事项

1. 确保服务器正在运行且可访问
2. 流式响应(stream=true)目前可能不完全支持
3. 模型参数(model)主要用于标识，实际使用的模型由服务器配置决定
4. 多轮对话使用thread_id参数来维护上下文

## 故障排除

1. **连接错误**: 确保服务器正在运行，检查URL和端口是否正确
2. **认证错误**: 检查API密钥是否正确设置
3. **请求格式错误**: 确保请求体是有效的JSON格式，包含所有必需字段
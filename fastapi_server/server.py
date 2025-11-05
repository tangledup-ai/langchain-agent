from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
import os
import sys
import time
import uvicorn
import httpx
import openai
import json
from loguru import logger

# 添加父目录到系统路径，以便导入lang_agent模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lang_agent.pipeline import Pipeline, PipelineConfig

# 定义OpenAI格式的请求模型
class ChatMessage(BaseModel):
    role: str = Field(..., description="消息角色，可以是 'system', 'user', 'assistant'")
    content: str = Field(..., description="消息内容")

class ChatCompletionRequest(BaseModel):
    model: str = Field(default="qwen-flash", description="模型名称")
    messages: List[ChatMessage] = Field(..., description="对话消息列表")
    temperature: Optional[float] = Field(default=0.7, description="采样温度")
    max_tokens: Optional[int] = Field(default=500, description="最大生成token数")
    stream: Optional[bool] = Field(default=False, description="是否流式返回")
    thread_id: Optional[int] = Field(default=3, description="线程ID，用于多轮对话")
    llm_provider: Optional[str] = Field(default="openai", description="LLM提供商")
    base_url: Optional[str] = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1", description="LLM API基础URL")

class ChatCompletionResponseChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str

class ChatCompletionResponseUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionResponseChoice]
    usage: Optional[ChatCompletionResponseUsage] = None

# OpenAI客户端包装类
class OpenAIClientWrapper:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        model_name: str = "qwen-flash",
        max_tokens: int = 500,
        temperature: float = 0.7,
        top_p: float = 1.0,
        frequency_penalty: float = 0.0,
    ):
        """
        初始化OpenAI客户端包装器
        
        Args:
            api_key: API密钥，如果为None则从环境变量OPENAI_API_KEY获取
            base_url: API基础URL，如果为None则从环境变量OPENAI_BASE_URL获取
            timeout: 请求超时时间（秒）
            model_name: 默认模型名称
            max_tokens: 默认最大token数
            temperature: 默认采样温度
            top_p: 默认top_p参数
            frequency_penalty: 默认频率惩罚
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", None)
        self.timeout = timeout
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.frequency_penalty = frequency_penalty
        
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout)
        )
    
    def response(self, session_id: str, dialogue: List[Dict[str, str]], **kwargs):
        """
        生成聊天响应（流式）
        
        Args:
            session_id: 会话ID
            dialogue: 对话消息列表，格式为 [{"role": "user", "content": "..."}, ...]
            **kwargs: 额外的参数，可以覆盖默认的max_tokens, temperature, top_p, frequency_penalty
        
        Returns:
            OpenAI流式响应对象
        """
        try:
            responses = self.client.chat.completions.create(
                model=self.model_name,
                messages=dialogue,
                stream=True,
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                temperature=kwargs.get("temperature", self.temperature),
                top_p=kwargs.get("top_p", self.top_p),
                frequency_penalty=kwargs.get("frequency_penalty", self.frequency_penalty),
            )
            return responses
        except Exception as e:
            logger.error(f"OpenAI客户端响应错误: {str(e)}")
            raise

# 初始化FastAPI应用
app = FastAPI(title="Lang Agent Chat API", description="使用OpenAI格式调用pipeline.invoke的聊天API")

# 设置API密钥
API_KEY = "123tangledup-ai"

# 创建安全方案
security = HTTPBearer()

# 验证API密钥的依赖项
# async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
#     if credentials.credentials != API_KEY:
#         raise HTTPException(
#             status_code=401,
#             detail="无效的API密钥",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
#     return credentials

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化Pipeline
pipeline_config = PipelineConfig()
pipeline_config.llm_name = "qwen-flash"
pipeline_config.llm_provider = "openai"
pipeline_config.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

pipeline = Pipeline(pipeline_config)

# 初始化OpenAI客户端包装器（可选，用于直接调用OpenAI API）
openai_client = OpenAIClientWrapper(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    timeout=60.0,
    model_name="qwen-flash",
    max_tokens=500,
    temperature=0.7,
    top_p=1.0,
    frequency_penalty=0.0,
)

def generate_streaming_chunks(full_text: str, response_id: str, model: str, chunk_size: int = 10):
    """
    Generate streaming chunks from non-streaming result
    """
    created_time = int(time.time())
    
    # Stream content chunks
    for i in range(0, len(full_text), chunk_size):
        chunk = full_text[i:i + chunk_size]
        if chunk:
            chunk_data = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": chunk},
                        "finish_reason": None
                    }
                ]
            }
            yield f"data: {json.dumps(chunk_data)}\n\n"
    
    # Send final chunk with finish_reason
    final_chunk = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": created_time,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }
        ]
    }
    yield f"data: {json.dumps(final_chunk)}\n\n"
    yield "data: [DONE]\n\n"

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest#, 
    # credentials: HTTPAuthorizationCredentials = Depends(verify_api_key)
):
    """
    使用OpenAI格式的聊天完成API
    """
    try:
        # 提取用户消息
        user_message = None
        system_message = None
        
        # TODO: wrap this sht as human and system message
        for message in request.messages:
            if message.role == "user":
                user_message = message.content
            elif message.role == "system" or message.role == "assistant":
                system_message = message.content
        
        if not user_message:
            raise HTTPException(status_code=400, detail="缺少用户消息")
        
        # 调用pipeline的chat方法 (always get non-streaming result)
        response_content = pipeline.chat(
            inp=user_message,
            as_stream=False,  # Always get full result, then chunk it if streaming
            thread_id=request.thread_id
        )
        
        # Ensure response_content is a string
        if not isinstance(response_content, str):
            response_content = str(response_content)
        
        logger.info(f"Pipeline response - Length: {len(response_content)}, Content: {repr(response_content[:200])}")
        
        if len(response_content) == 0:
            logger.warning("Pipeline returned empty response!")
        
        response_id = f"chatcmpl-{os.urandom(12).hex()}"
        
        # If streaming requested, return streaming response
        if request.stream:
            return StreamingResponse(
                generate_streaming_chunks(
                    full_text=response_content,
                    response_id=response_id,
                    model=request.model,
                    chunk_size=10
                ),
                media_type="text/event-stream"
            )
        
        # Otherwise return normal response
        response = ChatCompletionResponse(
            id=response_id,
            created=int(time.time()),
            model=request.model,
            choices=[
                ChatCompletionResponseChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=response_content),
                    finish_reason="stop"
                )
            ]
        )
        
        return response
    
    except Exception as e:
        logger.error(f"处理聊天请求时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")

@app.get("/")
async def root():
    """
    根路径，返回API信息
    """
    return {
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

@app.get("/health")
async def health_check():
    """
    健康检查接口
    """
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8488,
        reload=True
    )
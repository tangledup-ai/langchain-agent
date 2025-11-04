from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
import os
import sys
import time
import uvicorn
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

# 初始化FastAPI应用
app = FastAPI(title="Lang Agent Chat API", description="使用OpenAI格式调用pipeline.invoke的聊天API")

# 设置API密钥
API_KEY = "123tangledup-ai"

# 创建安全方案
security = HTTPBearer()

# 验证API密钥的依赖项
async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    if credentials.credentials != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="无效的API密钥",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest, 
    credentials: HTTPAuthorizationCredentials = Depends(verify_api_key)
):
    """
    使用OpenAI格式的聊天完成API
    """
    try:
        # 提取用户消息
        user_message = None
        system_message = None
        
        for message in request.messages:
            if message.role == "user":
                user_message = message.content
            elif message.role == "system" or message.role == "assistant":
                system_message = message.content
        
        if not user_message:
            raise HTTPException(status_code=400, detail="缺少用户消息")
        
        # 动态创建PipelineConfig
        pipeline_config = PipelineConfig()
        pipeline_config.llm_name = request.model
        pipeline_config.llm_provider = request.llm_provider
        pipeline_config.base_url = request.base_url
        
        # 创建新的Pipeline实例
        pipeline = Pipeline(pipeline_config)
        
        # 调用pipeline的chat方法
        response_content = pipeline.chat(
            inp=user_message,
            as_stream=request.stream,
            thread_id=request.thread_id
        )
        
        # 构建响应
        response = ChatCompletionResponse(
            id=f"chatcmpl-{os.urandom(12).hex()}",
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
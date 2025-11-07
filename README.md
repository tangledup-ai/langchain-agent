# langchain-agent

## 项目概述

这是一个基于LangChain和LangGraph构建的智能代理系统，集成了RAG(检索增强生成)、工具调用和WebSocket通信功能。项目主要用于茶饮场景的智能对话和订单处理，支持多种工具调用和远程MCP(Model Context Protocol)服务器集成。

## 项目结构

```
langchain-agent/
├── lang_agent/                    # 核心模块目录
│   ├── base.py                    # 基础抽象类定义
│   ├── config.py                  # 配置管理系统
│   ├── pipeline.py                # 主流程控制模块
│   ├── mcp_server.py              # MCP服务器实现
│   ├── tool_manager.py            # 工具管理器
│   ├── client_tool_manager.py     # 客户端工具管理器
│   ├── graphs/                    # 图工作流模块
│   │   ├── routing.py             # 路由图实现
│   │   └── react.py               # ReAct图实现
│   ├── rag/                       # RAG模块
│   │   ├── simple.py              # 简单RAG实现
│   │   └── emb.py                 # 文本嵌入模型
│   ├── dummy/                     # 示例工具
│   │   └── calculator.py          # 计算器工具
│   └── eval/                      # 评估模块
│       ├── evaluator.py           # 评估器
│       └── validator.py           # 验证器
├── scripts/                       # 可执行脚本目录
│   ├── run_agent_server.py        # 启动代理服务器
│   ├── start_mcp_server.py        # 启动MCP服务器
│   ├── ws_start_register_tools.py # WebSocket工具注册
│   ├── ws_start_all_mcps.py       # 启动所有MCP服务
│   ├── demo_chat.py               # 聊天演示
│   ├── make_rag_database.py       # 创建RAG数据库
│   ├── make_eval_dataset.py       # 创建评估数据集
│   └── eval.py                    # 评估脚本
├── configs/                       # 配置文件目录
│   ├── mcp_config.json            # MCP配置
│   ├── ws_mcp_config.json         # WebSocket MCP配置
│   └── route_sys_prompts/         # 路由系统提示
│       ├── chat_prompt.txt        # 聊天提示
│       ├── route_prompt.txt       # 路由提示
│       └── tool_prompt.txt        # 工具提示
└── fastapi_server/                # FastAPI服务器模块
    ├── server.py                  # 服务器实现
    ├── server_dashscope.py        # DashScope服务器
    └── test_*.py                  # 测试客户端
```

## 核心模块功能

### 1. 基础模块 (lang_agent/base.py)

定义了两个抽象基类：
- `LangToolBase`: 所有工具的基类，要求实现`get_tool_fnc`方法返回工具函数列表
- `GraphBase`: 所有图工作流的基类，要求实现`invoke`方法执行工作流

### 2. 配置管理 (lang_agent/config.py)

实现了灵活的配置系统：
- `PrintableConfig`: 提供配置打印和敏感信息脱敏功能
- `InstantiateConfig`: 支持通过`_target`属性动态实例化类
- `KeyConfig`: 管理API密钥，从环境变量加载
- `ToolConfig`: 控制工具使用开关
- 提供配置加载、合并和MCP配置转换等工具函数

### 3. 图工作流模块 (lang_agent/graphs/)

#### 路由图 (routing.py)
实现了基于决策的智能路由系统：
- `RoutingConfig`: 配置LLM参数和路由选项
- `RoutingGraph`: 构建状态图工作流，包含路由节点、聊天模型节点和工具模型节点
- 工作流程：通过LLM决策将请求路由到"chat"或"order"路径，分别调用不同的工具集

#### ReAct图 (react.py)
实现了ReAct(Reason-Act)模式的智能体：
- `ReactGraphConfig`: 配置ReAct图的参数
- `ReactGraph`: 使用LangChain的create_agent创建智能体，支持流式输出
- 集成ToolManager管理工具调用

### 4. 工具管理系统

#### 工具管理器 (lang_agent/tool_manager.py)
核心工具管理模块：
- `ToolManagerConfig`: 配置各种工具(RAG、计算器等)
- `ToolManager`: 统一管理工具实例化与调用
- 支持本地工具和MCP客户端工具的整合
- 将工具转换为LangChain的StructuredTool格式

#### 客户端工具管理器 (lang_agent/client_tool_manager.py)
管理MCP客户端工具：
- `ClientToolManagerConfig`: 管理MCP配置文件路径
- `ClientToolManager`: 通过MultiServerMCPClient从MCP服务器获取工具

### 5. RAG模块 (lang_agent/rag/)

#### 简单RAG (simple.py)
基础检索实现：
- `SimpleRagConfig`: 配置嵌入模型和数据库路径
- `SimpleRag`: 使用QwenEmbeddings和FAISS向量存储实现检索功能
- 支持相似度搜索和结果序列化

#### 嵌入模型 (emb.py)
文本嵌入实现：
- `QwenEmbeddings`: 继承LangChain的Embeddings基类
- 使用DashScope API实现文本嵌入
- 支持批量和单文本嵌入、同步和异步处理
- 包含速率限制、并发控制和错误处理机制

### 6. MCP服务器 (lang_agent/mcp_server.py)

实现MCP服务器功能：
- `MCPServerConfig`: 配置服务器名称、主机、端口和传输方式
- `MCPServer`: 使用FastMCP创建服务器，注册工具管理器中的工具
- 支持CORS配置和多种传输方式(stdio, sse, streamable-http)

### 7. 主流程控制 (lang_agent/pipeline.py)

项目的核心流程控制：
- `PipelineConfig`: 配置LLM参数、服务器设置和图配置
- `Pipeline`: 实现模块初始化、图工作流调用、WebSocket服务器和聊天接口
- 集成RoutingGraph或ReactGraph作为工作流引擎
- 提供带角色设定的对话逻辑

## 系统工作流程

1. **初始化阶段**:
   - 加载配置和环境变量
   - 初始化LLM、嵌入模型和工具管理器
   - 构建图工作流(RoutingGraph或ReactGraph)

2. **请求处理阶段**:
   - 接收用户输入
   - 通过图工作流进行路由决策或ReAct推理
   - 调用相应工具(RAG检索、计算器、远程MCP工具等)
   - 生成响应并返回

3. **扩展功能**:
   - WebSocket服务器支持实时通信
   - MCP协议支持远程工具调用
   - 评估系统支持模型性能测试

## 安装与配置

### 1. 安装依赖

```bash
# 安装xiaoliang-catering以支持购物车工具；否则，请在lang_agent/tool_manager.py中注释掉
pip install xiaoliang-catering

# 开发模式安装
python -m pip install -e .
```

### 2. 环境变量配置

需要设置以下环境变量：

```bash
export ALI_API_KEY=你的阿里云API密钥
export ALI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export MCP_ENDPOINT=你的MCP端点
export LANGSMITH_API_KEY=你的LangSmith API密钥
```

## 运行指南

### 1. 启动MCP服务器

```bash
# 1. 确保所有环境变量已设置
# 2. 启动MCP服务器
python scripts/start_mcp_server.py

# 3. 使用上述命令中的链接更新configs/ws_mcp_config.json
# 4. 启动WebSocket工具注册
python scripts/ws_start_register_tools.py
```

### 2. 运行代理服务器

```bash
python scripts/run_agent_server.py
```

### 3. 演示聊天

```bash
python scripts/demo_chat.py
```

### 4. 创建RAG数据库

```bash
python scripts/make_rag_database.py
```

### 5. 运行评估

```bash
# 创建评估数据集
python scripts/make_eval_dataset.py

# 运行评估
python scripts/eval.py
```

## 评估数据集格式

评估数据集格式如下，详见`scripts/make_eval_dataset.py`：

```json
[
    {
        "inputs": {"text": "用retrieve查询光予尘然后介绍"}, // 模型输入；使用列表进行对话
        "outputs": {"answer": "光予尘茉莉绿茶为底",         // 参考答案
                    "tool_use": ["retrieve"]}            // 工具使用；如果提供了多个工具，假设模型需要使用所有工具
    }
]
```

## 技术栈

- **核心框架**: LangChain, LangGraph
- **嵌入模型**: QwenEmbeddings (DashScope API)
- **向量存储**: FAISS
- **Web框架**: FastAPI, WebSocket
- **协议支持**: MCP (Model Context Protocol)
- **配置管理**: Tyro, YAML
- **日志系统**: Loguru

## 扩展指南

### 添加新工具

1. 在`lang_agent/dummy/`或其他适当目录创建新工具类，继承`LangToolBase`
2. 实现`get_tool_fnc`方法返回工具函数列表
3. 在`lang_agent/tool_manager.py`中注册新工具
4. 更新相关配置文件

### 添加新图工作流

1. 在`lang_agent/graphs/`目录创建新图类，继承`GraphBase`
2. 实现`invoke`方法执行工作流
3. 在`lang_agent/pipeline.py`中添加新图类型支持
4. 更新配置文件以支持新图类型

### 添加新评估指标

1. 在`lang_agent/eval/`目录扩展评估器或验证器
2. 在`scripts/eval.py`中集成新指标
3. 更新评估数据集格式以支持新指标
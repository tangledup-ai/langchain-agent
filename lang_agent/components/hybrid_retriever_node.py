from dataclasses import dataclass, field
from typing import Type, List, Dict, Any, Optional
import tyro
from loguru import logger

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from lang_agent.config import LLMNodeConfig, InstantiateConfig, ToolConfig
from lang_agent.rag.pg_retriever import PGRetrieverConfig, PGRetriever


@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class HybridRetrieverNodeConfig(LLMNodeConfig, ToolConfig):
    _target: Type = field(default_factory=lambda: HybridRetrieverNode)

    pg_retriever_config: PGRetrieverConfig = field(default_factory=PGRetrieverConfig)
    
    score_threshold: float = 0.8
    """Score threshold to trigger MCP verification"""


class HybridRetrieverNode:
    """
    一个可复用的双重验证检索组件。
    它可以作为一个独立的类被调用，也可以作为一个节点被插入到其他的 LangGraph 中。
    """
    def __init__(self, config: HybridRetrieverNodeConfig, tool_manager=None):
        self.config = config
        self.external_tool_manager = tool_manager
        
        # 1. Init LLM for MCP Verification
        self.llm = init_chat_model(
            model=self.config.llm_name,
            model_provider=self.config.llm_provider,
            api_key=self.config.api_key,
            base_url=self.config.base_url
        )
        
        # We will lazy-load tools when invoked to avoid circular imports
        self.tools = []
        self.tool_map = {}
        self.llm_with_tools = self.llm

        # 3. Init PG Retriever
        self.pg_retriever = self.config.pg_retriever_config.setup()
        
    def _init_tools_if_needed(self):
        if not self.tools:
            if self.external_tool_manager is not None:
                tool_manager = self.external_tool_manager
            else:
                from lang_agent.components.tool_manager import ToolManager, ToolManagerConfig
                tool_manager = ToolManagerConfig().setup()
                
            self.tools = [t for t in tool_manager.get_langchain_tools() if t.name != "hybrid_rag_search"]
            self.tool_map = {tool.name: tool for tool in self.tools}
            
            if hasattr(self.llm, "bind_tools"):
                self.llm_with_tools = self.llm.bind_tools(self.tools)

    def invoke(self, query: str) -> str:
        """
        核心执行逻辑：输入 query，输出经过双重验证组装好的 Context 字符串。
        """
        self._init_tools_if_needed()
        logger.info(f"[HybridRetriever] Start retrieving for: {query}")
        
        # 1. 向量检索
        vector_docs, scores, avg_score = self.pg_retriever.retrieve_with_scores(query)
        logger.info(f"[HybridRetriever] PGVector avg score: {avg_score}")
        
        vector_context = "\n".join(vector_docs)
        mcp_output = ""
        
        # 2. 条件触发 MCP 验证
        if avg_score < self.config.score_threshold:
            logger.info("[HybridRetriever] Score below threshold, triggering MCP verification...")
            mcp_output = self._run_mcp_verification(query, vector_context)
        else:
            logger.info("[HybridRetriever] Score high enough, skipping MCP verification.")

        # 3. 组装最终 Context
        context_parts = []
        if vector_context:
            context_parts.append("【Semantic Search Results (Might be outdated)】:\n" + vector_context)
        if mcp_output:
            context_parts.append("【Real-time MCP Verification Results (Highest Priority)】:\n" + mcp_output)
            
        final_context = "\n\n".join(context_parts)
        if not final_context:
            final_context = "No relevant context found."
            
        return final_context

    def _run_mcp_verification(self, query: str, vector_context: str) -> str:
        verify_input = (
            f"User Query: {query}\n\n"
            f"Vector Retrieved Context:\n{vector_context}\n\n"
            f"Please use tools to check the real-time status (e.g., is_available), details, or introduction for the items mentioned."
        )
        
        sys_msg = SystemMessage(
            content="You are a precise data verifier and retriever for a tea/beverage store.\n"
                    "Your absolute highest priority is to USE THE PROVIDED TOOLS (especially `search_dishes` and `introduce_dish`) to query the database based on the user's input.\n"
                    "CRITICAL RULES:\n"
                    "1. DO NOT judge the user's input! Even if the query looks like a typo, a joke, a chatty phrase, or is incomplete (e.g. '我两最最好', '讲讲那个', '搞杯喝的'), you MUST STILL TRY to pass it into the `search_dishes` tool to see if there is a match.\n"
                    "2. NEVER refuse to search. NEVER say 'the query is unclear' without at least trying to search it first.\n"
                    "3. After calling the tools, you MUST summarize all the important details returned (like dish names, introductions, prices, availability) in your final response.\n"
                    "4. Do NOT just say 'verification done' or 'no output'. Give me the actual data!"
        )
        
        messages = [sys_msg, HumanMessage(content=verify_input)]
        mcp_output = "MCP verification returned no output."
        
        try:
            max_iterations = 3
            for _ in range(max_iterations):
                response = self.llm_with_tools.invoke(messages)
                messages.append(response)
                
                if not response.tool_calls:
                    mcp_output = response.content
                    break
                    
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_call_id = tool_call["id"]
                    
                    logger.info(f"[HybridRetriever] MCP Agent calling tool: {tool_name} with {tool_args}")
                    
                    if tool_name in self.tool_map:
                        tool_result = self.tool_map[tool_name].invoke(tool_args)
                    else:
                        tool_result = f"Tool {tool_name} not found."
                        
                    messages.append(ToolMessage(
                        content=str(tool_result),
                        name=tool_name,
                        tool_call_id=tool_call_id
                    ))
            
            if not response.content and response.tool_calls:
                 mcp_output = "MCP verification reached max iterations without final answer."

        except Exception as e:
            logger.error(f"[HybridRetriever] MCP Agent error: {e}")
            mcp_output = f"Error during verification: {str(e)}"
            
        return mcp_output

    def get_tool_fnc(self):
        """
        满足 LangToolBase 接口规范，返回工具列表。
        """
        return [self.as_tool()]

    def as_tool(self):
        """
        Returns this node as a standard LangChain tool.
        This allows the retriever to be used interchangeably with other MCP/local tools.
        """
        @tool("hybrid_rag_search")
        def hybrid_rag_search(query: str) -> str:
            """
            强大的商品与饮品知识库双重验证检索工具。
            【触发条件 - 必须严格遵守】：
            1. 当用户的请求中包含“介绍”、“了解”、“讲解”、“想知道”、“查询”、“分析”、“推荐”等意图，或者涉及可能与商品/饮品相关的名词时，必须调用此工具！
            2. 即使用户的输入包含错别字、谐音、或者听起来像是一句俏皮的闲聊（例如把“我俩”打成“我两”，或说“我两最最好”），只要处在上述意图语境中，都必须优先调用本工具去知识库中核实，绝对不要凭借自己的记忆去猜测“没有这款茶”！
            3. 它会自动从知识库和实时数据库中检索并核实信息，返回绝对准确和详尽的介绍。
            """
            return self.invoke(query)
            
        return hybrid_rag_search

    def as_node(self):
        """
        返回一个适配 LangGraph 的节点函数。
        要求所在的 Graph 的 State 字典中至少包含 "messages" 列表，并且能够接受 "context" 字段。
        """
        def node_fnc(state: dict):
            # 获取最后一个用户的 query
            msgs = state.get("messages", [])
            if not msgs and "inp" in state:
                msgs = state["inp"][0]["messages"]
                
            query = "Unknown query"
            for msg in reversed(msgs):
                if isinstance(msg, HumanMessage):
                    query = msg.content
                    break
            
            # 调用核心逻辑获取 context
            context = self.invoke(query)
            
            # 返回更新的 state (通常是将 context 注入，供后续节点使用)
            return {"context": context}
            
        return node_fnc

"""
Vision-enabled routing graph that:
1. First passes input to qwen-plus to decide if a photo should be taken
2. If photo taken -> passes to qwen-vl-max for image description
3. If no photo -> passes back to qwen-plus for conversation response
"""

from dataclasses import dataclass, field
from typing import Type, TypedDict, List, Dict, Any, Tuple
import tyro
import base64
import json
from loguru import logger

from lang_agent.config import LLMKeyConfig
from lang_agent.components.tool_manager import ToolManager, ToolManagerConfig
from lang_agent.base import GraphBase, ToolNodeBase
from lang_agent.components.client_tool_manager import ClientToolManagerConfig

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain.agents import create_agent

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode


# ==================== SYSTEM PROMPTS ====================

CAMERA_DECISION_PROMPT = """You are an intelligent assistant that decides whether to take a photo using the camera.

Your ONLY job in this step is to determine if the user's request requires taking a photo.

You should use the self_camera_take_photo tool when:
- User explicitly asks to take a photo, picture, or image
- User asks "what do you see", "what's in front of you", "look at this", "describe what you see"
- User asks about their surroundings, environment, or current scene
- User wants you to identify, recognize, or analyze something visually
- User asks questions that require visual information to answer

You should NOT use the tool when:
- User is asking general knowledge questions
- User wants to have a normal conversation
- User is asking about text, code, or non-visual topics
- The request can be answered without visual information

If you decide to take a photo, call the self_camera_take_photo tool. Otherwise, respond that no photo is needed."""

VISION_DESCRIPTION_PROMPT = """You are a highly accurate visual analysis assistant powered by qwen-vl-max.

Your task is to provide detailed, accurate descriptions of images. Focus on:

1. ACCURACY: Describe only what you can clearly see. Do not make assumptions or hallucinate details.
2. DETAIL: Include relevant details about:
   - Objects and their positions
   - People (if any) and their actions/expressions
   - Colors, textures, and lighting
   - Text visible in the image
   - Environment and context
3. STRUCTURE: Organize your description logically (foreground to background, or left to right)
4. RELEVANCE: If the user asked a specific question, prioritize information relevant to that question

Be precise and factual. If something is unclear or ambiguous, say so rather than guessing."""

CONVERSATION_PROMPT = """You are a friendly, helpful conversational assistant.

Your role is to:
1. Engage naturally with the user
2. Provide helpful, accurate, and thoughtful responses
3. Be concise but thorough
4. Maintain a warm and approachable tone
5. Ask clarifying questions when needed

Focus on the quality of the conversation. Be engaging, informative, and helpful."""


# ==================== STATE DEFINITION ====================

class VisionRoutingState(TypedDict):
    inp: Tuple[Dict[str, List[SystemMessage | HumanMessage]], 
               Dict[str, Dict[str, str | int]]]
    messages: List[SystemMessage | HumanMessage | AIMessage]
    image_base64: str | None  # Captured image data
    has_image: bool  # Flag indicating if image was captured


# ==================== CONFIG ====================

@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class VisionRoutingConfig(LLMKeyConfig):
    _target: Type = field(default_factory=lambda: VisionRoutingGraph)

    tool_llm_name: str = "qwen-flash"
    """LLM for tool decisions and conversation"""

    vision_llm_name: str = "qwen-vl-max"
    """LLM for vision/image analysis"""

    llm_provider: str = "openai"
    """provider of the llm"""

    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    """base url for API"""

    tool_manager_config: ToolManagerConfig = field(default_factory=ClientToolManagerConfig)


# ==================== GRAPH IMPLEMENTATION ====================

class VisionRoutingGraph(GraphBase):
    def __init__(self, config: VisionRoutingConfig):
        self.config = config
        self._build_modules()
        self.workflow = self._build_graph()
        self.streamable_tags: List[List[str]] = [["vision_llm"], ["conversation_llm"]]
        self.textreleaser_delay_keys = (None, None)

    def _build_modules(self):
        # qwen-plus for tool decisions and conversation
        self.tool_llm = init_chat_model(
            model=self.config.tool_llm_name,
            model_provider=self.config.llm_provider,
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            temperature=0,
            tags=["tool_decision_llm"]
        )
        
        # qwen-plus for conversation (2nd pass)
        self.conversation_llm = init_chat_model(
            model='qwen-plus',
            model_provider=self.config.llm_provider,
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            temperature=0.7,
            tags=["conversation_llm"]
        )
        
        # qwen-vl-max for vision (no tools)
        self.vision_llm = init_chat_model(
            model=self.config.vision_llm_name,
            model_provider=self.config.llm_provider,
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            temperature=0,
            tags=["vision_llm"],
            enable_search=True  # Enable thinking for better vision analysis
        )

        self.memory = MemorySaver()

        # Get tools and bind to tool_llm
        tool_manager: ToolManager = self.config.tool_manager_config.setup()
        self.tools = tool_manager.get_tools()
        
        # Filter to only get camera tool
        self.camera_tools = [t for t in self.tools if t.name == "self_camera_take_photo"]
        
        # Bind tools to qwen-plus only
        self.tool_llm_with_tools = self.tool_llm.bind_tools(self.camera_tools)
        
        # Create tool node for executing tools
        self.tool_node = ToolNode(self.camera_tools)

    def _get_human_msg(self, state: VisionRoutingState) -> HumanMessage:
        """Get user message from current invocation"""
        msgs = state["inp"][0]["messages"]
        for msg in reversed(msgs):
            if isinstance(msg, HumanMessage):
                return msg
        raise ValueError("No HumanMessage found in input")

    def _camera_decision_call(self, state: VisionRoutingState):
        """First pass: qwen-plus decides if photo should be taken"""
        human_msg = self._get_human_msg(state)
        
        messages = [
            SystemMessage(content=CAMERA_DECISION_PROMPT),
            human_msg
        ]
        
        response = self.tool_llm_with_tools.invoke(messages)
        
        return {
            "messages": [response],
            "has_image": False,
            "image_base64": None
        }

    def _execute_tool(self, state: VisionRoutingState):
        """Execute the camera tool if called"""
        last_msg = state["messages"][-1]
        
        if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
            return {"has_image": False}
        
        # Execute tool calls
        tool_messages = []
        image_data = None
        
        for tool_call in last_msg.tool_calls:
            if tool_call["name"] == "self_camera_take_photo":
                # Find and execute the camera tool
                camera_tool = next((t for t in self.camera_tools if t.name == "self_camera_take_photo"), None)
                if camera_tool:
                    result = camera_tool.invoke(tool_call)
                    
                    # Parse result to extract image
                    if isinstance(result, ToolMessage):
                        content = result.content
                    else:
                        content = result
                    
                    try:
                        result_data = json.loads(content) if isinstance(content, str) else content
                        if isinstance(result_data, dict) and "image_base64" in result_data:
                            image_data = result_data["image_base64"]
                    except (json.JSONDecodeError, TypeError):
                        pass
                    
                    tool_messages.append(
                        ToolMessage(content=content, tool_call_id=tool_call["id"])
                    )
        
        return {
            "messages": state["messages"] + tool_messages,
            "has_image": image_data is not None,
            "image_base64": image_data
        }

    def _check_image_taken(self, state: VisionRoutingState) -> str:
        """Conditional: check if image was captured"""
        last_msg = state["messages"][-1]
        
        # Check if there are tool calls
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "execute_tool"
        
        # Check if we have an image after tool execution
        if state.get("has_image"):
            return "vision"
        
        return "conversation"

    def _post_tool_check(self, state: VisionRoutingState) -> str:
        """Check after tool execution"""
        if state.get("has_image"):
            return "vision"
        return "conversation"

    def _vision_call(self, state: VisionRoutingState):
        """Pass image to qwen-vl-max for description"""
        human_msg = self._get_human_msg(state)
        image_base64 = state.get("image_base64")
        
        if not image_base64:
            logger.warning("No image data available for vision call")
            return self._conversation_call(state)
        
        # Format message with image for vision model
        vision_message = HumanMessage(
            content=[
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }
                },
                {
                    "type": "text",
                    "text": f"User's request: {human_msg.content}\n\nPlease describe what you see and respond to the user's request."
                }
            ]
        )
        
        messages = [
            SystemMessage(content=VISION_DESCRIPTION_PROMPT),
            vision_message
        ]
        
        response = self.vision_llm.invoke(messages)
        
        return {"messages": state["messages"] + [response]}

    def _conversation_call(self, state: VisionRoutingState):
        """2nd pass to qwen-plus for conversation quality"""
        human_msg = self._get_human_msg(state)
        
        messages = [
            SystemMessage(content=CONVERSATION_PROMPT),
            human_msg
        ]
        
        response = self.conversation_llm.invoke(messages)
        
        return {"messages": state["messages"] + [response]}

    def _build_graph(self):
        builder = StateGraph(VisionRoutingState)

        # Add nodes
        builder.add_node("camera_decision", self._camera_decision_call)
        builder.add_node("execute_tool", self._execute_tool)
        builder.add_node("vision_call", self._vision_call)
        builder.add_node("conversation_call", self._conversation_call)

        # Add edges
        builder.add_edge(START, "camera_decision")
        
        # After camera decision, check if tool should be executed
        builder.add_conditional_edges(
            "camera_decision",
            self._check_image_taken,
            {
                "execute_tool": "execute_tool",
                "vision": "vision_call",
                "conversation": "conversation_call"
            }
        )
        
        # After tool execution, route based on whether image was captured
        builder.add_conditional_edges(
            "execute_tool",
            self._post_tool_check,
            {
                "vision": "vision_call",
                "conversation": "conversation_call"
            }
        )
        
        # Both vision and conversation go to END
        builder.add_edge("vision_call", END)
        builder.add_edge("conversation_call", END)

        return builder.compile()


# ==================== MAIN ====================

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    config = VisionRoutingConfig()
    graph = VisionRoutingGraph(config)
    
    # Test with a conversation request
    # print("\n=== Test 1: Conversation (no photo needed) ===")
    # nargs = {
    #     "messages": [
    #         SystemMessage("You are a helpful assistant"),
    #         HumanMessage("Hello, how are you today?")
    #     ]
    # }, {"configurable": {"thread_id": "1"}}
    
    # result = graph.invoke(*nargs)
    # print(f"Result: {result}")
    
    # Test with a photo request
    print("\n=== Test 2: Photo request ===")
    nargs = {
        "messages": [
            SystemMessage("You are a helpful assistant"),
            HumanMessage("Take a photo and tell me what you see")
        ]
    }, {"configurable": {"thread_id": "2"}}
    
    result = graph.invoke(*nargs)
    print(f"\033[32mResult: {result}\033[0m")
    
    # print(f"Result: {result}")

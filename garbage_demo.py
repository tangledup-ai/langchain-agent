import time, threading
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain.chat_models import init_chat_model
import dotenv, os

from langchain_core.messages.base import BaseMessageChunk
from langchain_core.messages import BaseMessage, AIMessage
from langchain.agents import create_agent
dotenv.load_dotenv()


# --- Shared state ---
class State(TypedDict):
    chat_active: bool
    tool_done: Annotated[bool, lambda a, b: a or b]
    tool_result: str
    chat_output: Annotated[str, lambda a, b: a + b]


RUN_STATE = {"tool_done": False}

CHAT_MODEL = init_chat_model(
        model="qwen-flash",
        model_provider="openai",
        api_key=os.environ.get("ALI_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=0,
    )


# CHAT_MODEL = create_agent(CHAT_MODEL, [], checkpointer=MemorySaver())

# --- Nodes ---
def tool_node(state: State):
    """Simulate background work."""
    def work():
        for i in range(3):
            print(f"\033\n[33m[Tool] Working... {i+1}/3\033[0m")
            time.sleep(2)
        print("[Tool] Done.")
        RUN_STATE["tool_done"] = True

    work()
    return {"tool_done": False, "tool_result": "WEEEEEE, TOOL WORKS BABAY!"}


def chat_node(state: State):
    """Chat repeatedly until tool is finished."""

    output = ""
    i = 1
    while not RUN_STATE["tool_done"]:
        msg = {"role": "user", "content": f"Tool not done yet (step {i})"}
        resp = CHAT_MODEL.invoke([{"role": "system", "content": "Keep the user updated."}, msg])
        text = getattr(resp, "content", str(resp))
        output += f"[Chat] {text}\n"
        i += 1
        time.sleep(1)

    output += "\n[Chat] Tool done detected.\n"
    return {"chat_output": output}


def handoff_node(state: State):
    final = f"Tool result: {state.get('tool_result', 'unknown')}"
    print("[Handoff]", final)
    return {"chat_output": state.get("chat_output", "") + final}


# --- Graph ---
builder = StateGraph(State)
builder.add_node("tool_node", tool_node)
builder.add_node("chat_node", chat_node)
builder.add_node("handoff_node", handoff_node)

builder.add_edge(START, "tool_node")
builder.add_edge(START, "chat_node")
builder.add_edge("chat_node", "handoff_node")
builder.add_edge("tool_node", "handoff_node")
builder.add_edge("handoff_node", END)

graph = builder.compile(checkpointer=MemorySaver())

# from PIL import Image
# import matplotlib.pyplot as plt
# from io import BytesIO

# img = Image.open(BytesIO(graph.get_graph().draw_mermaid_png()))
# plt.imshow(img)
# plt.show()

# --- Streaming Run ---
print("\n=== STREAM MODE: messages ===\n")
state0 = (
    {"chat_active": True, "tool_done": False, "tool_result": "", "chat_output": ""},
    {"configurable": {"thread_id": 1}},
)

# for event in graph.stream(*state0, stream_mode="messages"):
#     print("[STREAM UPDATE]:", event)


for chunk in graph.stream(*state0, stream_mode="updates"):
    # node = metadata.get("langgraph_node")
    # if node not in ("model"):
        # continue  # skip router or other intermediate nodes

    # Print only the final message content
    if isinstance(chunk, (BaseMessageChunk, BaseMessage)) and getattr(chunk, "content", None):
        print(chunk.content, end="", flush=True)


print("\n=== Run Finished ===")

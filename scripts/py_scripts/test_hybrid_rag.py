import sys
import os.path as osp
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

# Ensure project root is in python path
sys.path.append(osp.dirname(osp.dirname(osp.dirname(osp.abspath(__file__)))))

from lang_agent.graphs.hybrid_rag import HybridRagGraphConfig, HybridRagGraph

def main():
    print("Loading environment variables...")
    load_dotenv()
    
    print("Initializing HybridRagGraph...")
    # 你可以在这里修改参数，比如 score_threshold 等
    # 因为我们重构了节点，score_threshold 现在属于 retriever_node_config
    from lang_agent.components.hybrid_retriever_node import HybridRetrieverNodeConfig
    config = HybridRagGraphConfig(
        llm_name="qwen-plus", # 根据你的实际大模型名称调整
        retriever_node_config=HybridRetrieverNodeConfig(score_threshold=0.8)
    )
    
    try:
        graph: HybridRagGraph = config.setup()
        print("Graph initialized successfully!\n")
    except Exception as e:
        print(f"Failed to initialize graph: {e}")
        return

    print("==================================================")
    print("Hybrid RAG Test Terminal")
    print("Type 'exit' or 'quit' to stop.")
    print("==================================================\n")

    thread_id = "test_thread_1"

    while True:
        try:
            user_input = input("\033[92mUser:\033[0m ")
            if user_input.lower() in ["exit", "quit"]:
                break
            if not user_input.strip():
                continue
                
            print("\033[94mAgent:\033[0m ", end="", flush=True)
            
            # 使用流式输出
            for chunk in graph.invoke(
                {"messages": [HumanMessage(content=user_input)]},
                {"configurable": {"thread_id": thread_id}},
                as_stream=True
            ):
                # LangGraph 可能会吐出 dict 或者 AIMessageChunk
                if isinstance(chunk, dict):
                    # 如果是最终节点的输出字典，比如 {"generate": {"messages": [AIMessage(...)]}}
                    for node_name, node_state in chunk.items():
                        if "messages" in node_state and len(node_state["messages"]) > 0:
                            last_msg = node_state["messages"][-1]
                            if hasattr(last_msg, "content"):
                                # 在非流式节点中，只打印最终结果
                                print(last_msg.content, end="", flush=True)
                elif hasattr(chunk, "content"):
                    # 如果是真正的流式 token
                    print(chunk.content, end="", flush=True)
                elif isinstance(chunk, str):
                    print(chunk, end="", flush=True)
            print("\n")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\nError during inference: {e}\n")

if __name__ == "__main__":
    main()

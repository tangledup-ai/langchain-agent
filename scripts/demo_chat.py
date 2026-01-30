import tyro
from typing import Annotated

from lang_agent.pipeline import Pipeline, PipelineConfig
from lang_agent.config import load_tyro_conf


def main(
    conf: PipelineConfig,
    stream: Annotated[bool, tyro.conf.arg(name="stream")] = True,
):
    """Demo chat script for langchain-agent pipeline.
    
    Args:
        conf: Pipeline configuration
        stream: Enable streaming mode for chat responses
    """
    if conf.config_f is not None:
        conf = load_tyro_conf(conf.config_f)
    
    pipeline: Pipeline = conf.setup()
    
    while True:
        user_input = input("请讲：")
        if user_input.lower() == "exit":
            break
        
        if stream:
            # Streaming mode: print chunks as they arrive
            print("回答: ", end="", flush=True)
            for chunk in pipeline.chat(user_input, as_stream=True):
                print(chunk, end="", flush=True)
            print()  # New line after streaming completes
        else:
            # Non-streaming mode: print full response
            response = pipeline.chat(user_input, as_stream=False)
            print(f"回答: {response}")


if __name__ == "__main__":
    tyro.cli(main)
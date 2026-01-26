import tyro
import asyncio
from loguru import logger

from lang_agent.pipeline import Pipeline, PipelineConfig
from lang_agent.config import load_tyro_conf

def main(conf:PipelineConfig):
    if conf.config_f is not None:
        conf = load_tyro_conf(conf.config_f)
    
    pipeline:Pipeline = conf.setup()
    
    while True:
        user_input = input("请讲：")
        if user_input.lower() == "exit":
            break
        response = pipeline.chat(user_input)
        # print(f"回答: {response}")

    # # out = pipeline.chat("用工具算6856854-416846等于多少;然后解释它是怎么算出来的", as_stream=True)
    # out = pipeline.chat("你叫什么名字，我今天心情不好，而且天气也不好，我想去外面玩，帮我计划一下", as_stream=True)
    # # out = pipeline.chat("testing", as_stream=True)
    # print("=========== final ==========")
    # print(out)


if __name__ == "__main__":
    main(tyro.cli(PipelineConfig))
import tyro
import asyncio

from lang_agent.pipeline import Pipeline, PipelineConfig
from lang_agent.config import load_tyro_conf

def main(conf:PipelineConfig):
    if conf.config_f is not None:
        conf = load_tyro_conf(conf.config_f)
    
    pipeline:Pipeline = conf.setup()
    
    # while True:
        
    #     user_input = input("请讲：")
    #     if user_input.lower() == "exit":
    #         break
    #     response = pipeline.chat(user_input, as_stream=True)
    #     print(f"回答: {response}")

    # out = pipeline.chat("用工具算6856854-416846等于多少;然后解释它是怎么算出来的", as_stream=True)
    out = pipeline.chat("介绍一下自己", as_stream=True)
    # out = pipeline.chat("testing", as_stream=True)
    print("=========== final ==========")
    print(out)


if __name__ == "__main__":
    main(tyro.cli(PipelineConfig))
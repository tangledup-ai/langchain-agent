import tyro
import asyncio

from lang_agent.pipeline import Pipeline, PipelineConfig
from lang_agent.config import load_config

def main(conf:PipelineConfig):
    if conf.config_f is not None:
        conf = load_config(conf.config_f)
    
    pipeline:Pipeline = conf.setup()
    asyncio.run(pipeline.start_server())


if __name__ == "__main__":
    main(tyro.cli(PipelineConfig))
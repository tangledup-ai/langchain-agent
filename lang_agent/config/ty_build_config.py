import tyro
from loguru import logger
import os
import os.path as osp
from lang_agent.pipeline import PipelineConfig

def build_conf(pipeline:PipelineConfig, save_path:str):
    os.makedirs(osp.dirname(save_path), exist_ok=True)
    logger.info(pipeline)
    pipeline.save_config(save_path)

if __name__ == "__main__":
    tyro.cli(build_conf)
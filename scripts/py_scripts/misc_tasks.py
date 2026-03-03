from lang_agent.graphs import ReactGraphConfig, ReactGraph, RoutingConfig,RoutingGraph
from lang_agent.pipeline import PipelineConfig
from lang_agent.base import GraphBase

import os.path as osp
import os
from tqdm import tqdm
import yaml
import tyro
from loguru import logger

def gen_arch_imgs(save_dir="frontend/assets/images/graph_arch"):

    save_dir = osp.join(osp.dirname(osp.dirname(__file__)), save_dir)
    confs:GraphBase = [ReactGraphConfig(), RoutingConfig()]
    for conf in tqdm(confs):
        graph:GraphBase = conf.setup()
        img = graph.show_graph(ret_img=True)
        img.save(osp.join(save_dir, f"arch_{conf.__class__.__name__}.png"))


def make_save_conf(pipeline:PipelineConfig, save_path:str):
    os.makedirs(osp.dirname(save_path), exist_ok=True)
    logger.info(pipeline)
    pipeline.save_config(save_path)

if __name__ == "__main__":
    # gen_arch_imgs()
    tyro.cli(make_save_conf)
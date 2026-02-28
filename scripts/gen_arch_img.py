from lang_agent.graphs import ReactGraphConfig, ReactGraph, RoutingConfig,RoutingGraph
from lang_agent.base import GraphBase

import os.path as osp
from tqdm import tqdm

def main():

    save_dir = osp.join(osp.dirname(osp.dirname(__file__)), "frontend/assets/images/graph_arch")
    confs:GraphBase = [ReactGraphConfig(), RoutingConfig()]
    for conf in tqdm(confs):
        graph:GraphBase = conf.setup()
        img = graph.show_graph(ret_img=True)
        img.save(osp.join(save_dir, f"arch_{conf.__class__.__name__}.png"))

if __name__ == "__main__":
    main()
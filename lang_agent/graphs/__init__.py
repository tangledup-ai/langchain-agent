import tyro

from lang_agent.graphs.react import ReactGraphConfig
from lang_agent.graphs.routing import RoutingConfig
from lang_agent.graphs.dual_path import DualConfig
from lang_agent.graphs.vision_routing import VisionRoutingConfig
# from lang_agent.graphs.xiaoai_demo import XiaoAiConfig

graph_dict = {
    "react": ReactGraphConfig(),
    "route": RoutingConfig(),
    "dual": DualConfig(),
    "vision": VisionRoutingConfig(),
    # "ai_demo": XiaoAiConfig()
}

graph_union = tyro.extras.subcommand_type_from_defaults(graph_dict, prefix_names=False)
AnnotatedGraph = tyro.conf.OmitSubcommandPrefixes[tyro.conf.SuppressFixed[graph_union]]
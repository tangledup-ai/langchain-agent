import tyro

from lang_agent.graphs.react import ReactGraphConfig, ReactGraph
from lang_agent.graphs.routing import RoutingConfig, RoutingGraph
from lang_agent.graphs.dual_path import DualConfig, Dual
from lang_agent.graphs.vision_routing import VisionRoutingConfig, VisionRoutingGraph

graph_dict = {
    "react": ReactGraphConfig(),
    "route": RoutingConfig(),
    "dual": DualConfig(),
    "vision": VisionRoutingConfig()
}

graph_union = tyro.extras.subcommand_type_from_defaults(graph_dict, prefix_names=False)
AnnotatedGraph = tyro.conf.OmitSubcommandPrefixes[tyro.conf.SuppressFixed[graph_union]]
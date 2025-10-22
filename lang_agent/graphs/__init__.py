import tyro

from lang_agent.graphs.react import ReactGraphConfig
from lang_agent.graphs.routing import RoutingConfig

graph_dict = {
    "react": ReactGraphConfig(),
    "route": RoutingConfig()
}

graph_union = tyro.extras.subcommand_type_from_defaults(graph_dict, prefix_names=False)
AnnotatedGraph = tyro.conf.OmitSubcommandPrefixes[tyro.conf.SuppressFixed[graph_union]]
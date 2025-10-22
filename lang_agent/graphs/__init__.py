import tyro

from lang_agent.graphs.react import ReactGraphConfig

graph_dict = {
    "react": ReactGraphConfig()
}

graph_union = tyro.extras.subcommand_type_from_defaults(graph_dict, prefix_names=False)
AnnotatedGraph = tyro.conf.OmitSubcommandPrefixes[tyro.conf.SuppressFixed[graph_union]]
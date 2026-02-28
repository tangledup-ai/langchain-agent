import tyro

from lang_agent.fs_bkends.base import BaseFilesystemBackend
from lang_agent.fs_bkends.statebk import StateBk, StateBkConfig

statebk_dict = {
    "statebk": StateBkConfig(),
}

statebk_union = tyro.extras.subcommand_type_from_defaults(statebk_dict, prefix_names=False)
AnnotatedStateBk = tyro.conf.OmitSubcommandPrefixes[tyro.conf.SuppressFixed[statebk_union]]
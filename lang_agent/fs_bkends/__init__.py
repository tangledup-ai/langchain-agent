import tyro

from lang_agent.fs_bkends.base import BaseFilesystemBackend
from lang_agent.fs_bkends.statebk import StateBk, StateBkConfig
from lang_agent.fs_bkends.localshell import LocalShell, LocalShellConfig
from lang_agent.fs_bkends.daytona_sandbox import DaytonaSandboxBk, DaytonaSandboxConfig

statebk_dict = {
    "statebk": StateBkConfig(),
    "localshell": LocalShellConfig(),
    "daytonasandbox": DaytonaSandboxConfig(),
}

statebk_union = tyro.extras.subcommand_type_from_defaults(statebk_dict, prefix_names=False)
AnnotatedStateBk = tyro.conf.OmitSubcommandPrefixes[tyro.conf.SuppressFixed[statebk_union]]
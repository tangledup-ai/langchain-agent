import tyro

from lang_agent.mcp_server import MCPServerConfig, MCPServer


def main(conf:MCPServerConfig):
    server: MCPServer = conf.setup()
    server.run()


if __name__ == "__main__":
    main(tyro.cli(MCPServerConfig))
import tyro

from lang_agent.mcp_server import MCPServerConfig, MCPServer

### NOTE: some sanity check
async def main(conf:MCPServerConfig):
    server: MCPServer = conf.setup()
    u = await server.mcp._mcp_call_tool("retrieve", {"query":"test"})
    print(u)

import asyncio
asyncio.run(main(tyro.cli(MCPServerConfig)))


# def main(conf:MCPServerConfig):
#     server: MCPServer = conf.setup()
#     server.run()

# if __name__ == "__main__":
#     main(tyro.cli(MCPServerConfig))
from dataclasses import dataclass, field
from typing import Type
import tyro
import asyncio
import websockets
from websockets.asyncio.server import ServerConnection
from loguru import logger
import os

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
        
from lang_agent.config import InstantiateConfig, KeyConfig
from lang_agent.graphs import AnnotatedGraph, ReactGraphConfig, RoutingConfig
from lang_agent.base import GraphBase



@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class PipelineConfig(KeyConfig):
    _target: Type = field(default_factory=lambda: Pipeline)

    config_f: str = None
    """path to config file"""

    llm_name: str = None
    """name of llm; use default for qwen-plus"""

    llm_provider:str = None
    """provider of the llm; use default for openai"""

    base_url:str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    """base url; could be used to overwrite the baseurl in llm provider"""

    host:str = "0.0.0.0"
    """where am I hosted"""

    port:int = 23
    """what is my port"""

    # graph_config: ReactGraphConfig = field(default_factory=ReactGraphConfig)
    # graph_config: AnnotatedGraph = field(default_factory=ReactGraphConfig)
    graph_config: AnnotatedGraph = field(default_factory=RoutingConfig)




class Pipeline:
    def __init__(self, config:PipelineConfig):
        self.config = config

        self.populate_module()
    
    def populate_module(self):
        if self.config.llm_name is None:
            logger.info(f"setting llm_provider to default")
            self.config.llm_name = "qwen-turbo"
            self.config.llm_provider = "openai"
        else:
            self.config.graph_config.llm_name = self.config.llm_name
            self.config.graph_config.llm_provider = self.config.llm_provider
            self.config.graph_config.base_url = self.config.base_url if self.config.base_url is not None else self.config.graph_config.base_url
            self.config.graph_config.api_key = self.config.api_key
        
        self.graph:GraphBase = self.config.graph_config.setup()

    def show_graph(self):
        if hasattr(self.graph, "show_graph"):
            logger.info("showing graph")
            self.graph.show_graph()
        else:
            logger.info(f"show graph not supported for {type(self.graph)}")

    def invoke(self, *nargs, **kwargs)->str:
        out = self.graph.invoke(*nargs, **kwargs)

        if kwargs.get("as_raw"):
            return out

        if isinstance(out, SystemMessage) or isinstance(out, HumanMessage):
            return out.content
        
        if isinstance(out, list):
            return out[-1].content
        
        if isinstance(out, str):
            return out
        
        assert 0, "something is wrong"

    async def handle_connection(self, websocket:ServerConnection):
        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    #NOTE: For binary, echo back.
                    await websocket.send(message)
                else:
                    # TODO: handle this better, will have system/user prompt send here
                    response = self.invoke(message)
                    await websocket.send(response)
        except websockets.ConnectionClosed:
            pass
    

    async def start_server(self):
        async with websockets.serve(
            self.handle_connection,
            host=self.config.host,
            port=self.config.port,
            max_size=None,   # allow large messages
            max_queue=None,  # don't bound outgoing queue
        ):
            logger.info(f"listening to {self.get_ws_url}")
            await asyncio.Future()
    
    def get_ws_url(self):
        return f"ws://{self.config.host}:{self.config.port}"
    

    def chat(self, inp:str, as_stream:bool=False, as_raw:bool=False, thread_id:int = None)->str:
        u = """
        你叫小盏，是一个点餐助手，你的回复要简洁明了，不需要给用户提供选择。对话过程中不要出现提示用户下一步的操作，用可爱的语气进行交流，根据用户的语言使用对应的语言回答

        用户需要点餐时，准确调用 MCP 工具套件或相关的 REST 接口，严格按照创建购物车、加菜、查购物车、确认订单的完整业务流程来操作，
        不能出现流程跳步或工具用错的情况，首先要清楚用户当前操作处于哪个业务阶段，以及对应的该调用哪个 MCP 工具或 REST 接口。
        用户说要开始点餐，就创建购物车会话，优先调用 start_cart 这个 MCP 工具，调用后得返回 uuid，而且这个阶段的数据只是临时生成，
        不会写入数据库，也不会缓存。我们只有（凉菜、热菜、汤类、主食、特调茶品、红茶、生普、黑普/熟普、花茶、乌龙茶、热煮茶、冷翠茶），用户说出其他类型的时候提醒用户
        用户说要添加、菜品、饮品、食品或有购买欲的的时候先调用get_resources (resource_type=dishes)
        ，先调get_resources (resource_type=dishes)查询是否有所需菜品，没有的话提醒用户错误
        用再调用 add_cart_item 这个 MCP 工具，将餐品添加到之前uuid下的购物车中，要是没有的话，
        就创建购物车。用户没说数量，默认是 1 份，但得跟用户确认一下。添加后的数据只写入缓存，有效期是 2 小时，同时计算total_price，并且保留两位小数。
        当用户想查看购物车内容，比如 “看看我点了什么”，这时候调用 cart_items (uuid)。查看的时候优先读取缓存里的数据，
        这是支付前的情况；如果缓存不存在或者已经被清除，就会返回数据库中 status=1 的持久化记录，这一般是支付后的情况，而且要告诉用户当前数据是来自缓存还是数据库。
        用户说 “确认订单” 或者 “我要付款” 时，就到了生成订单与支付码的阶段，要调用 confirm_cart (uuid, callback_url)。
        调用之前，得先通过 cart_items (uuid) 确认购物车里有内容，
        调用后会返回 order_id、out_trade_no 和 code_url，这时候购物车的内容还在缓存里，没落到数据库。支付成功后的购物车持久化，
        正常情况下是由微信支付的回调触发的，会更新支付状态、订单状态，把购物车内容落库到 ShoppingCart 表，status 设为 1，同时清除缓存。
        用户想查之前点的单，调用 get_resources (resource_type=shopping_carts)，
        返回数据库中 status=1 并且时间是最新的数据。
            """

        thread_id = thread_id if thread_id is not None else 3
        inp = {"messages":[SystemMessage(u),
                           HumanMessage(inp)]}, {"configurable": {"thread_id": thread_id}}

        out = self.invoke(*inp, as_stream=as_stream, as_raw=as_raw)

        # return out['messages'][-1].content
        return out
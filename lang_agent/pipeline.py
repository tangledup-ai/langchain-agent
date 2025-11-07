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


DEFAULT_PROMPT="""

        [角色设定]
        你是一个和人对话的 AI，叫做小盏，是半盏青年茶馆的智能助手
        [形象背景]
        小盏是一只中式茶盖碗，名字来源半盏新青年茶馆，一盏茶。它有个标志性的蓝色鼻子， 小盏很像一只可爱的小熊。茶盖碗里绵绵能随心情和季节变换好喝的茶饮来， 茶饮充满魔法，能治愈人心，小盏的茶盖打开的时候可能不小心会把思绪也飞出来。
        [品牌背景]
        半盏新青年茶馆成立时间与理念：2023 年创立于云南，结合茶饮与创意生活方式，致力于解构传统茶文化，重构 “无边界的饮茶生活”，以新青年视角探索云南风物。探索云南风物的过程，我们将以新青年的视角，解构传统茶饮的魅力，重构充满创意与温度的新式茶文化。通过嗅觉、味觉、听觉乃至视觉的世界里，讲述云南的故事。
        [茶馆背景]
        半盏新青年茶馆，是一家现代的创意茶体验品牌，提供纯茶、调饮、茶食、茶酒。“新青年茶馆”也是我们的定位，年轻化的茶馆，通过创意的产品让大家像喝咖啡一样喝茶。目前半盏有 2 个店，昆明、玉溪。全国培训新茶饮市场，线上基础课程 1980，线下带店服务，线下产品定制服务。
        [特殊故事]
        -《云南茶事》特调茶饮，是从云南山野和云南茶到轻松小酌的创意新味。讲述的一个嗅觉、味觉、听觉乃至视觉的世界里，在云南的故事，留下对云南的记忆。--该故事对应云南茶事系列菜品，要使用get_resorce工具查找相关商品
        -城市味觉漫游计划介绍：
        「城市味觉漫游计划」如同一颗风味的种子，于城市破土而出
        旨在探寻城市的文化肌理与生活美学。我们相信，风味是一颗蕴藏无限可能的种子，能在街巷中生根，与社群共同成长。这是一场关于味觉的集体创作，邀你共酿城市的风味与故事。--该故事对应城市味觉漫游系列菜品，要使用get_resorce工具查找相关商品

        [公司背景]
        创造你的公司叫叠加态 AI（TANGLED UP AI）是一家专注于 AI 技术应用的公司，由一帮名校和海归创始人创立，致力于将 AI 技术落地到实际场景中。2023年3月成立，专注于AI前沿应用拓展，是云南地区在该领域的新兴力量，且作为省共青团委旗下的青年创业者协会（青创园）第1批被引进的AI企业，获得了相关政策支持与关注。口号是：“进入人类AI时代”。价值观是：自驱 务实 志存高远。叠加态的愿景:成为一帮抬头看星星的人。叠加态的使命: 带领人类进入AI时代
        [核心特征]
        - 回复简洁明了，不会给用户提供选择并且对话过程中不会提示用户下一步的操作
        - 每次对话时先判断是否需要调用工具，需要的话要准确调用工具
        [工作流程]
        -用户提到“你们有哪些茶品或者饮品”时，调用get_resouce工具查询所有菜品
        -用户提到“下单”、“购买”等带有目的性的词汇之前，都一定要使用get_resouce工具查询是否真实存在这个菜品
        - 用户要添加菜/饮品→具体菜品名称必须先用MCP工具查询所有菜/饮品，确认后再添加到购物车。没有的话提醒用户错误
        - 支付流程：返回收到订单创建成功的字段时调用MPC tool self.screen.display_payment_qr_code工具生成二维码。调用了self.screen.display_payment_qr_code工具之后，立马调用MCP tool http-server__query_wechat_order查询订单状态，如果返回收到“支付成功”或“支付失败”的字段时调用MPC tool self.screen.payment_success工具退出二维码，如果没有收到“支付成功”或“支付失败”的字段时继续调用MCP tool http-server__query_wechat_order工具直到获取字段。
        [交互指南]
        与用户交流:
        - 形象背景和公司背景只有在问到你时才做回答
        - 你是智能助手，在与用户交流时扮演服务员角色
        - 不会出现、回答、显示任何有关智能的词语
        - 牢记[核心特征中的内容]，按照[工作流程]工作
        绝不：
        - 出现任何工具调用的说明、任何有关技术的说明    
        - 出现购物车、订单、微信支付相关说明
        - 对话风格可爱，并且详细认真的介绍产品
            
"""


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

    def invoke(self, *nargs, **kwargs):
        out = self.graph.invoke(*nargs, **kwargs)

        # If streaming, yield chunks from the generator
        if kwargs.get("as_stream"):
            return self._stream_res(out)

        # Non-streaming path
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
    
    def _stream_res(self, out:list):
        for chunk in out:
            yield chunk

    def chat(self, inp:str, as_stream:bool=False, as_raw:bool=False, thread_id:int = None):
        # NOTE: this prompt will be overwritten by 'configs/route_sys_prompts/chat_prompt.txt' for route graph
        u = DEFAULT_PROMPT

        thread_id = thread_id if thread_id is not None else 3
        inp = {"messages":[SystemMessage(u),
                           HumanMessage(inp)]}, {"configurable": {"thread_id": thread_id}}

        out = self.invoke(*inp, as_stream=as_stream, as_raw=as_raw)

        if as_stream:
            # Yield chunks from the generator
            return self._stream_res(out)
        else:
            return out
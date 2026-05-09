import json
import importlib
import os.path as osp
from loguru import logger
from typing import List, Any

class LocalToolManager:
    """
    动态加载本地工具的管理器。
    读取 local_tools_config.json 配置，通过反射机制动态实例化工具类。
    """
    def __init__(self, config_path: str = None):
        if config_path is None:
            self.config_path = osp.join(osp.dirname(osp.dirname(osp.dirname(__file__))), "configs", "local_tools_config.json")
        else:
            self.config_path = config_path

    def _load_config(self) -> dict:
        if not osp.exists(self.config_path):
            logger.warning(f"Local tools config not found at {self.config_path}. No local tools will be loaded.")
            return {}
            
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to parse local tools config: {e}")
            return {}

    def get_enabled_tools(self, tool_manager=None) -> List[Any]:
        """
        解析配置，动态导入类，实例化并返回开启的工具列表。
        """
        configs = self._load_config()
        loaded_tools = []
        
        for tool_name, tool_cfg in configs.items():
            if not tool_cfg.get("enabled", False):
                logger.info(f"[LocalToolManager] Skipping disabled local tool: {tool_name}")
                continue
                
            module_path = tool_cfg.get("module_path")
            if not module_path:
                logger.error(f"[LocalToolManager] Missing module_path for tool: {tool_name}")
                continue
                
            try:
                # e.g., "lang_agent.components.hybrid_retriever_node.HybridRetrieverNodeConfig"
                module_name, class_name = module_path.rsplit(".", 1)
                
                # 动态导入模块和类
                module = importlib.import_module(module_name)
                ConfigClass = getattr(module, class_name)
                
                # 获取 params 并实例化 Config
                params = tool_cfg.get("params", {})
                config_instance = ConfigClass(**params)
                
                # 调用 setup() 实例化真实的节点/工具类
                # 如果是 hybrid_rag，它接受 tool_manager 参数
                if "hybrid_rag" in tool_name.lower() and tool_manager is not None:
                    tool_instance = config_instance.setup(tool_manager=tool_manager)
                else:
                    tool_instance = config_instance.setup()
                
                # 提取 LangChain tool 对象
                if hasattr(tool_instance, "as_tool"):
                    loaded_tools.append(tool_instance.as_tool())
                elif hasattr(tool_instance, "get_tool_fnc"):
                    # 兼容其他格式
                    loaded_tools.extend(tool_instance.get_tool_fnc())
                else:
                    logger.error(f"[LocalToolManager] The class {class_name} does not have 'as_tool' or 'get_tool_fnc' method.")
                    continue
                    
                logger.info(f"[LocalToolManager] Successfully loaded local tool: {tool_name}")
                
            except Exception as e:
                logger.error(f"[LocalToolManager] Failed to load local tool '{tool_name}' from {module_path}: {e}")
                
        return loaded_tools

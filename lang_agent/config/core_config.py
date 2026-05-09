from dataclasses import dataclass, is_dataclass, fields, MISSING
from typing import Any, Tuple, Type, Optional
import yaml
from pathlib import Path
from typing import Dict
import os

from loguru import logger
from dotenv import load_dotenv

load_dotenv()


def resolve_llm_api_key(api_key: Optional[str]) -> Optional[str]:
    """Resolve the API key for OpenAI-compatible providers."""
    if api_key not in (None, "", "wrong-key"):
        resolved_key = api_key
    else:
        resolved_key = os.environ.get("ALI_API_KEY") or os.environ.get("OPENAI_API_KEY")

    # Some OpenAI-compatible integrations still read OPENAI_API_KEY from env.
    if resolved_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = resolved_key

    return resolved_key

## NOTE: base classes taken from nerfstudio
class PrintableConfig:
    """
    Printable Config defining str function  
     定义 __str__ 方法的可打印配置类
    
    """

    def __str__(self):
        lines = [self.__class__.__name__ + ":"]
        for key, val in vars(self).items():

            if self.is_secrete(key):
                val = str(val)
                val = val[:3] + "*"*(len(val) - 6) + val[-3:]
                
            if isinstance(val, Tuple):
                flattened_val = "["
                for item in val:
                    flattened_val += str(item) + "\n"
                flattened_val = flattened_val.rstrip("\n")
                val = flattened_val + "]"
            lines += f"{key}: {str(val)}".split("\n")
        return "\n"  + "\n    ".join(lines)
    
    def is_secrete(self, inp:str):
        sec_list = ["secret", "api_key"]
        for sec in sec_list:
            if sec in inp:
                return True
        
        return False


# Base instantiate configs
@dataclass
class InstantiateConfig(PrintableConfig):
    """
    Config class for instantiating an the class specified in the _target attribute.
    
    用于实例化 _target 属性指定的类的配置类
    
    """

    _target: Type

    def setup(self, **kwargs) -> Any:
        """
        Returns the instantiated object using the config.
        
        使用配置返回实例化的对象
        
        """
        return self._target(self, **kwargs)
    
    def save_config(self, filename: str) -> None:
        """
        Save the config to a YAML file.
        
        将配置保存到 YAML 文件
        
        """
        # Persist the full config object (including type tags) so it can be
        # deserialized back into config instances with methods like .setup().
        # Secret masking is intentionally handled by __str__ for printing/logging,
        # not when writing to disk.
        with open(filename, "w", encoding="utf-8") as f:
            yaml.dump(self, f)
        logger.info(f"[yellow]config saved to: {filename}[/yellow]")
    
    def get_name(self):
        return self.__class__.__name__


@dataclass
class LLMKeyConfig(InstantiateConfig):
    llm_name: str = "qwen-plus"
    """name of llm"""

    llm_provider:str = "openai"
    """provider of the llm"""

    base_url:str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    """base url; could be used to overwrite the baseurl in llm provider"""

    api_key:str = None
    """api key for llm"""

    def __post_init__(self):
        original_api_key = self.api_key
        self.api_key = resolve_llm_api_key(self.api_key)
        if self.api_key is None:
            logger.error("no ALI_API_KEY or OPENAI_API_KEY provided for embedding")
        elif original_api_key in (None, "", "wrong-key"):
            logger.info("LLM API key loaded from environment")

        original_base_url = self.base_url
        if self.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1":
            env_base_url = os.environ.get("ALI_BASE_URL")
            if env_base_url:
                self.base_url = env_base_url
                logger.info("LLM base_url loaded from environment")
            else:
                self.base_url = original_base_url

        env_llm_name = os.environ.get("LLM_NAME")
        if env_llm_name:
            self.llm_name = env_llm_name
            logger.info("LLM llm_name loaded from environment")


@dataclass
class LLMNodeConfig(LLMKeyConfig):
    """
    class is for LLM nodes that has system prompt config
    """

    pipeline_id: Optional[str] = None
    """If set, load prompts from database (with file fallback)"""

    prompt_set_id: Optional[str] = None
    """If set, load from this specific prompt set instead of the active one"""


@dataclass
class ToolConfig(InstantiateConfig):
    use_tool:bool = True
    """
    specify to use tool or not
    
    指定是否使用工具
    """

def load_tyro_conf(filename: str, inp_conf = None) -> InstantiateConfig:
    """
    load and overwrite config from file
    
    从文件加载并覆盖配置
    
    """
    config = yaml.load(Path(filename).read_text(), Loader=yaml.Loader)

    # config = ovewrite_config(config, inp_conf) if inp_conf is not None else config
    return config

def is_default(instance, field_):
    """
    Check if the value of a field in a dataclass instance is the default value.
    
    检查数据类实例中字段的值是否为默认值
    
    """
    value = getattr(instance, field_.name)

    if field_.default is not MISSING:
        # Compare with default value   
        """
        与默认值进行比较
        
        如果字段有默认值，则将当前值与默认值进行比较
        
        """
        return value == field_.default
    elif field_.default_factory is not MISSING:
        # Compare with value generated by the default factory
        """
        与默认工厂生成的值进行比较
        
        如果字段有默认工厂，则将当前值与默认工厂生成的值进行比较
        
        """
        return value == field_.default_factory()
    else:
        # No default value specified
        return False

def ovewrite_config(loaded_conf, inp_conf):
    """
    for non-default values in inp_conf, overwrite the corresponding values in loaded_conf
    
    对于 inp_conf 中的非默认值，覆盖 loaded_conf 中对应的配置
    
    """
    if not (is_dataclass(loaded_conf) and is_dataclass(inp_conf)):
        return loaded_conf

    for field_ in fields(loaded_conf):
        field_name = field_.name
        """
        if field_name in inp_conf:
        
        如果字段名在 inp_conf 中，则进行覆盖
        
        """
        current_value = getattr(inp_conf, field_name)
        new_value = getattr(inp_conf, field_name) 
       
        """
         inp_conf[field_name]
        从 inp_conf 中获取字段值
        
        如果字段名在 inp_conf 中，则获取其值
        
        """

        if is_dataclass(current_value):
         
            """
            Recurse for nested dataclasses

            递归处理嵌套的数据类
            
            如果当前值是数据类，则递归调用 ovewrite_config 进行合并
            
            """
            merged_value = ovewrite_config(current_value, new_value)
            setattr(loaded_conf, field_name, merged_value)
        elif not is_default(inp_conf, field_):
            """
            Overwrite only if the current value is not default
            
            仅在当前值不是默认值时进行覆盖
            
            如果 inp_conf 中的字段值不是默认值，则覆盖 loaded_conf 中的对应值
            
            """
            setattr(loaded_conf, field_name, new_value)

    return loaded_conf
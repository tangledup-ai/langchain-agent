from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

import os
from dotenv import load_dotenv
load_dotenv()

def make_llm(model="qwen-plus",
             model_provider="openai",
             api_key=None,
             base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
             **kwargs)->BaseChatModel:
    api_key = os.environ.get("ALI_API_KEY") if api_key is None else api_key

    llm = init_chat_model(model=model,
                          model_provider=model_provider,
                          api_key=api_key,
                          base_url=base_url,
                          **kwargs)
    
    return llm
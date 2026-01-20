from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
import re

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

def tree_leaves(tree):
    """
    Extracts all leaf values from a nested structure (dict, list, tuple).
    Drop-in replacement for jax.tree.leaves.
    """
    leaves = []
    stack = [tree]
    
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            stack.extend(reversed(node.values()))
        elif isinstance(node, (list, tuple)):
            stack.extend(reversed(node))
        else:
            leaves.append(node)
    
    return leaves


NON_WORD_PATTERN = re.compile(r'[^\u4e00-\u9fffA-Za-z0-9_\s]')
def words_only(text):
    """
    Keep only:
        - Chinese characters (U+4E00–U+9FFF)
        - Latin letters, digits, underscore
        - Whitespace (as separators)
    Strip punctuation, emojis, etc.
    Return a list of tokens (Chinese blocks or Latin word blocks).
    """
    # 1. Replace all non-allowed characters with a space
    cleaned = NON_WORD_PATTERN.sub(' ', text)

    # 2. Normalize multiple spaces and split into tokens
    tokens = cleaned.split()

    return "".join(tokens)
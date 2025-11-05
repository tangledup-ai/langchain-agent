#!/usr/bin/env python3
"""
使用OpenAI Python客户端库调用我们的FastAPI聊天API的示例
"""

from openai import OpenAI
import os

# 设置API基础URL和API密钥（这里使用一个虚拟的密钥，因为我们没有实现认证）
client = OpenAI(
    api_key="your-api-key",  # 这里可以使用任意值，因为我们的API没有实现认证
    base_url="http://localhost:8000/v1"
)

def simple_chat():
    """简单的聊天示例"""
    print("=" * 50)
    print("简单聊天示例")
    print("=" * 50)
    
    response = client.chat.completions.create(
        model="qwen-flash",
        messages=[
            {"role": "user", "content": "你好，请介绍一下你自己。"}
        ],
        temperature=0.7,
        thread_id=1
    )
    
    print(f"助手回复: {response.choices[0].message.content}")
    print("\n")

def multi_turn_chat():
    """多轮对话示例"""
    print("=" * 50)
    print("多轮对话示例")
    print("=" * 50)
    
    # 第一轮对话
    print("第一轮对话:")
    response1 = client.chat.completions.create(
        model="qwen-flash",
        messages=[
            {"role": "user", "content": "你推荐什么茶？"}
        ],
        temperature=0.7,
        thread_id=2
    )
    
    print(f"用户: 你推荐什么茶？")
    print(f"助手: {response1.choices[0].message.content}")
    
    # 第二轮对话，使用相同的thread_id
    print("\n第二轮对话:")
    response2 = client.chat.completions.create(
        model="qwen-flash",
        messages=[
            {"role": "user", "content": "为什么推荐这个茶？"}
        ],
        temperature=0.7,
        thread_id=2  # 使用相同的thread_id
    )
    
    print(f"用户: 为什么推荐这个茶？")
    print(f"助手: {response2.choices[0].message.content}")
    print("\n")

def system_prompt_example():
    """使用系统提示的示例"""
    print("=" * 50)
    print("系统提示示例")
    print("=" * 50)
    
    response = client.chat.completions.create(
        model="qwen-flash",
        messages=[
            {"role": "system", "content": "你是一个专业的茶艺师，用简洁的语言回答问题，不超过50字。"},
            {"role": "user", "content": "请介绍一下普洱茶。"}
        ],
        temperature=0.3,
        thread_id=3
    )
    
    print(f"用户: 请介绍一下普洱茶。")
    print(f"助手: {response.choices[0].message.content}")
    print("\n")

def interactive_chat():
    """交互式聊天示例"""
    print("=" * 50)
    print("交互式聊天 (输入'quit'退出)")
    print("=" * 50)
    
    thread_id = 4  # 为这个会话分配一个固定的thread_id
    
    while True:
        user_input = input("你: ")
        if user_input.lower() == 'quit':
            break
        
        try:
            response = client.chat.completions.create(
                model="qwen-flash",
                messages=[
                    {"role": "user", "content": user_input}
                ],
                temperature=0.7,
                thread_id=thread_id
            )
            
            print(f"助手: {response.choices[0].message.content}")
        except Exception as e:
            print(f"错误: {str(e)}")

if __name__ == "__main__":
    print("使用OpenAI客户端库调用FastAPI聊天API示例")
    print("注意: 确保服务器在 http://localhost:8000 上运行\n")
    
    # 简单聊天示例
    simple_chat()
    
    # 多轮对话示例
    multi_turn_chat()
    
    # 系统提示示例
    system_prompt_example()
    
    # 交互式聊天示例
    interactive_chat()
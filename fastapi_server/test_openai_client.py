#!/usr/bin/env python3
"""
Simple test for OpenAI client chat.completions.create
"""
import os
import httpx
import openai
from dotenv import load_dotenv

load_dotenv()

print("Initializing OpenAI client...")
print(f"Base URL: http://localhost:8488/v1")
print(f"API Key set: {'Yes' if os.getenv('ALI_API_KEY') else 'No'}")

# Initialize client (pointing to FastAPI server from server.py)
client = openai.OpenAI(
    api_key=os.getenv("ALI_API_KEY"),
    base_url="http://localhost:8488/v1",
    timeout=httpx.Timeout(60.0)
)

print("\nTesting chat completion (non-streaming)...")
# try:
#     # Test chat completion (non-streaming first)
#     response = client.chat.completions.create(
#         model="qwen-flash",
#         messages=[
#             {'role':'system', 'content': 'your name is steve'}
#             ,{"role": "user", "content": "Say hello!"}],
#         stream=False,
#         max_tokens=100,
#         temperature=0.7
#     )
    
#     print(f"Response ID: {response.id}")
#     print(f"Model: {response.model}")
#     print(f"Content: {response.choices[0].message.content}")
#     print("\n✓ Non-streaming test successful!")
    
# except Exception as e:
#     print(f"\n✗ Error: {str(e)}")
#     import traceback
#     traceback.print_exc()

print("\nTesting chat completion (streaming)...")
try:
    # Test streaming with same message as non-streaming test
    response = client.chat.completions.create(
        model="qwen-flash",
        messages=[
            {'role':'system', 'content': 'your name is steve'},
            {"role": "user", "content": "Say hello!"}
        ],
        stream=True,
        max_tokens=100,
        temperature=0.7
    )
    
    print("Streaming response:")
    full_content = ""
    chunk_count = 0
    for chunk in response:
        chunk_count += 1
        if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
            if hasattr(chunk.choices[0], 'delta') and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                print(content, end="", flush=True)
                full_content += content
    
    print(f"\n\nTotal chunks received: {chunk_count}")
    print(f"Full content: {repr(full_content)}")
    print(f"Content length: {len(full_content)}")
    print("\n✓ Streaming test successful!")
    
except Exception as e:
    print(f"\n✗ Error: {str(e)}")
    import traceback
    traceback.print_exc()

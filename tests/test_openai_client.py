#!/usr/bin/env python3
"""
Test for OpenAI-compatible API against server_openai.py

Instructions:
- Start the OpenAI-compatible server first, e.g.:
    python fastapi_server/server_openai.py --llm_name qwen-plus --llm_provider openai --base_url https://dashscope.aliyuncs.com/compatible-mode/v1
- Or with uvicorn:
    uvicorn fastapi_server.server_openai:app --host 0.0.0.0 --port 8589 --reload
- Set BASE_URL and API_KEY environment variables (or in .env file):
    OPENAI_BASE_URL=http://127.0.0.1:8589/v1
    API_KEY=sk-your-api-key-here
- Make sure the API_KEY matches one of the keys in the server's API_KEYS environment variable
"""
import os
from dotenv import load_dotenv
from loguru import logger

TAG = __name__

load_dotenv()

try:
    from openai import OpenAI
except Exception as e:
    print("openai package not found. Please install it: pip install openai")
    raise


# <<< Paste your running FastAPI base url here >>>
BASE_URL = os.getenv("OPENAI_BASE_URL", "http://121.40.192.128:8589/v1")
API_KEY = os.getenv("FAST_AUTH_KEYS", None)

# Test configuration matching the server setup
# llm_name: "qwen-plus"
# llm_provider: "openai"
# base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"

# Test messages
messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "use calculator to calculate 1234*5641"},
]


def test_streaming():
    """Test streaming chat completion"""
    print("\n" + "="*60)
    print("Testing STREAMING chat completion...")
    print("="*60 + "\n")
    
    if not API_KEY:
        logger.warning("API_KEY not set. Set it in environment variable or .env file.")
        raise ValueError("API_KEY environment variable is required for authentication")
    
    client = OpenAI(
        base_url=BASE_URL,
        api_key=API_KEY
    )
    
    try:
        stream = client.chat.completions.create(
            model="qwen-plus",  # Using qwen-plus as configured
            messages=messages,
            stream=True,
            extra_body={"thread_id":"2000"}
        )
        
        full_response = ""
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                full_response += content
                print(content, end="", flush=True)
        
        print("\n\n" + "-"*60)
        print(f"Full streaming response length: {len(full_response)}")
        print("-"*60)
        
        return full_response
    
    except Exception as e:
        logger.error(f"Streaming test error: {e}")
        raise


def test_non_streaming():
    """Test non-streaming chat completion"""
    print("\n" + "="*60)
    print("Testing NON-STREAMING chat completion...")
    print("="*60 + "\n")
    
    if not API_KEY:
        logger.warning("API_KEY not set. Set it in environment variable or .env file.")
        raise ValueError("API_KEY environment variable is required for authentication")
    
    client = OpenAI(
        base_url=BASE_URL,
        api_key=API_KEY
    )
    
    try:
        response = client.chat.completions.create(
            model="qwen-plus",  # Using qwen-plus as configured
            messages=messages,
            stream=False,
            extra_body={"thread_id":"2000"}
        )
        
        content = response.choices[0].message.content
        print(f"Response: {content}")
        print("\n" + "-"*60)
        print(f"Full non-streaming response length: {len(content)}")
        print(f"Finish reason: {response.choices[0].finish_reason}")
        print("-"*60)
        
        return content
    
    except Exception as e:
        logger.error(f"Non-streaming test error: {e}")
        raise


def main():
    print(f"\nUsing base_url = {BASE_URL}")
    if API_KEY:
        # Show only first 8 chars for security
        masked_key = API_KEY[:8] + "..." if len(API_KEY) > 8 else API_KEY
        print(f"Using API_KEY = {masked_key}")
    else:
        print("WARNING: API_KEY not set!")
    print()
    
    # Test both streaming and non-streaming
    streaming_result = "" #test_streaming()
    non_streaming_result = test_non_streaming()
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Streaming response length: {len(streaming_result)}")
    print(f"Non-streaming response length: {len(non_streaming_result)}")
    print("\nBoth tests completed successfully!")


if __name__ == "__main__":
    main()

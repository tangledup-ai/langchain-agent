#!/usr/bin/env python3
"""
Simple chat loop to interact with the blueberry pipeline via DashScope-compatible API.

Usage:
    python scripts/py_scripts/chat_dashcope.py

The script connects to the server running on http://localhost:8500
and uses the API key from the pipeline registry.
"""

import requests
import json
import sys
from typing import Optional


# Configuration from pipeline_registry.json
API_KEY = "sk-6c7091e6a95f404efb2ec30e8f51b897626d670375cdf822d78262f24ab12367"
PIPELINE_ID = "blueberry"
BASE_URL = "http://localhost:8500"
SESSION_ID = "chat-session-1"


def send_message(
    message: str,
    session_id: str = SESSION_ID,
    stream: bool = False,
    app_id: str = PIPELINE_ID,
) -> Optional[str]:
    """Send a message to the blueberry pipeline and return the response."""
    url = f"{BASE_URL}/v1/apps/{app_id}/sessions/{session_id}/responses"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "messages": [
            {"role": "user", "content": message}
        ],
        "stream": stream,
    }
    
    try:
        if stream:
            # Handle streaming response
            response = requests.post(url, headers=headers, json=payload, stream=True)
            response.raise_for_status()
            
            accumulated_text = ""
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]  # Remove 'data: ' prefix
                        try:
                            data = json.loads(data_str)
                            output = data.get("output", {})
                            text = output.get("text", "")
                            if text:
                                accumulated_text = text
                                # Print incremental updates (you can modify this behavior)
                                print(f"\rAssistant: {accumulated_text}", end="", flush=True)
                            
                            if data.get("is_end", False):
                                print()  # New line after streaming completes
                                return accumulated_text
                        except json.JSONDecodeError:
                            continue
            return accumulated_text
        else:
            # Handle non-streaming response
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            output = data.get("output", {})
            return output.get("text", "")
            
    except requests.exceptions.RequestException as e:
        print(f"Error sending message: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json()
                print(f"Error details: {error_detail}", file=sys.stderr)
            except:
                print(f"Response status: {e.response.status_code}", file=sys.stderr)
        return None


def main():
    """Main chat loop."""
    print("=" * 60)
    print(f"Chat with Blueberry Pipeline")
    print(f"Pipeline ID: {PIPELINE_ID}")
    print(f"Server: {BASE_URL}")
    print(f"Session ID: {SESSION_ID}")
    print("=" * 60)
    print("Type your messages (or 'quit'/'exit' to end, 'stream' to toggle streaming)")
    print("Streaming mode is ON by default")
    print()
    
    stream_mode = True
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
                
            if user_input.lower() == 'stream':
                stream_mode = not stream_mode
                print(f"Streaming mode: {'ON' if stream_mode else 'OFF'}")
                continue
            
            print("Assistant: ", end="", flush=True)
            response = send_message(user_input, stream=stream_mode)
            
            if response is None:
                print("(No response received)")
            elif not stream_mode:
                print(response)
            # For streaming, the response is already printed incrementally
            
            print()  # Empty line for readability
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()


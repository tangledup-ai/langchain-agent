#!/usr/bin/env python3
"""
Integration tests for the REST API server (server_rest.py)

This script tests the REST API endpoints using FastAPI's TestClient.

To run:
    conda activate lang
    python test_rest_api.py

Or with pytest:
    conda activate lang
    pytest test_rest_api.py -v

Tests cover:
- Health check endpoints
- API key authentication
- Conversation creation
- Chat endpoint (streaming and non-streaming)
- Message creation (streaming and non-streaming)
- Memory deletion (global and per-conversation)
- Error handling

Requirements:
- pytest (for structured testing)
- Or run directly as a script
"""
import os
import sys
import json
from unittest.mock import AsyncMock, MagicMock, patch

# Set up test environment before importing the server
os.environ["FAST_AUTH_KEYS"] = "test-key-1,test-key-2,test-key-3"

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from fastapi.testclient import TestClient
    from langgraph.checkpoint.memory import MemorySaver
    HAS_TEST_CLIENT = True
except ImportError:
    HAS_TEST_CLIENT = False
    print("Warning: fastapi.testclient not available. Install with: pip install pytest httpx")
    print("Falling back to basic import test only.")

from fastapi_server.server_rest import app


def create_mock_pipeline():
    """Create a mock Pipeline instance for testing."""
    pipeline = MagicMock()
    
    # Mock async function that returns async generator for streaming or string for non-streaming
    async def mock_achat(inp, as_stream=False, thread_id="test"):
        if as_stream:
            # Return async generator for streaming
            async def gen():
                chunks = ["Hello", " ", "world", "!"]
                for chunk in chunks:
                    yield chunk
            return gen()
        else:
            # Return string for non-streaming
            return "Hello world!"
    
    async def mock_aclear_memory():
        return None
    
    pipeline.achat = AsyncMock(side_effect=mock_achat)
    pipeline.aclear_memory = AsyncMock(return_value=None)
    
    # Mock graph with memory
    mock_graph = MagicMock()
    mock_memory = MagicMock(spec=MemorySaver)
    mock_memory.delete_thread = MagicMock()
    mock_graph.memory = mock_memory
    pipeline.graph = mock_graph
    
    return pipeline


def test_health_endpoints():
    """Test health check endpoints."""
    print("\n=== Testing Health Endpoints ===")
    
    with patch("fastapi_server.server_rest.pipeline", create_mock_pipeline()):
        client = TestClient(app)
        
        # Test root endpoint
        response = client.get("/")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "message" in data, "Root endpoint should return message"
        assert "endpoints" in data, "Root endpoint should return endpoints list"
        print("✓ Root endpoint works")
        
        # Test health endpoint
        response = client.get("/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data["status"] == "healthy", "Health endpoint should return healthy status"
        print("✓ Health endpoint works")


def test_authentication():
    """Test API key authentication."""
    print("\n=== Testing Authentication ===")
    
    with patch("fastapi_server.server_rest.pipeline", create_mock_pipeline()):
        client = TestClient(app)
        
        # Test missing auth header
        response = client.post("/v1/conversations")
        assert response.status_code == 401, f"Expected 401 for missing auth, got {response.status_code}"
        print("✓ Missing auth header returns 401")
        
        # Test invalid API key
        response = client.post(
            "/v1/conversations",
            headers={"Authorization": "Bearer invalid-key"}
        )
        assert response.status_code == 401, f"Expected 401 for invalid key, got {response.status_code}"
        print("✓ Invalid API key returns 401")
        
        # Test valid API key
        response = client.post(
            "/v1/conversations",
            headers={"Authorization": "Bearer test-key-1"}
        )
        assert response.status_code == 200, f"Expected 200 for valid key, got {response.status_code}"
        print("✓ Valid API key works")
        
        # Test API key without Bearer prefix
        response = client.post(
            "/v1/conversations",
            headers={"Authorization": "test-key-1"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ API key without Bearer prefix works")


def test_conversation_creation():
    """Test conversation creation."""
    print("\n=== Testing Conversation Creation ===")
    
    with patch("fastapi_server.server_rest.pipeline", create_mock_pipeline()):
        client = TestClient(app)
        auth_headers = {"Authorization": "Bearer test-key-1"}
        
        response = client.post("/v1/conversations", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "id" in data, "Response should contain id"
        assert "created_at" in data, "Response should contain created_at"
        assert data["id"].startswith("c_"), "Conversation ID should start with 'c_'"
        print(f"✓ Created conversation: {data['id']}")


def test_chat_endpoint():
    """Test chat endpoint."""
    print("\n=== Testing Chat Endpoint ===")
    
    mock_pipeline = create_mock_pipeline()
    with patch("fastapi_server.server_rest.pipeline", mock_pipeline):
        client = TestClient(app)
        auth_headers = {"Authorization": "Bearer test-key-1"}
        
        # Test non-streaming chat
        response = client.post(
            "/v1/chat",
            headers=auth_headers,
            json={
                "input": "Hello, how are you?",
                "stream": False
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "conversation_id" in data, "Response should contain conversation_id"
        assert "output" in data, "Response should contain output"
        assert data["output"] == "Hello world!", "Output should match expected"
        print(f"✓ Non-streaming chat works: {data['conversation_id']}")
        
        # Test chat with existing conversation_id
        conv_id = "c_test123"
        response = client.post(
            "/v1/chat",
            headers=auth_headers,
            json={
                "input": "Hello",
                "conversation_id": conv_id,
                "stream": False
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data["conversation_id"] == conv_id, "Should use provided conversation_id"
        print(f"✓ Chat with existing conversation_id works")
        
        # Test streaming chat
        response = client.post(
            "/v1/chat",
            headers=auth_headers,
            json={
                "input": "Hello",
                "stream": True
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "text/event-stream" in response.headers["content-type"], "Should return event-stream"
        
        # Parse streaming response
        lines = response.text.split("\n")
        data_lines = [line for line in lines if line.startswith("data: ")]
        assert len(data_lines) > 0, "Should have streaming data"
        
        # Parse first delta event
        first_data = json.loads(data_lines[0][6:])  # Remove "data: " prefix
        assert first_data["type"] == "delta", "First event should be delta"
        assert "conversation_id" in first_data, "Delta should contain conversation_id"
        assert "delta" in first_data, "Delta should contain delta field"
        print("✓ Streaming chat works")


def test_message_endpoint():
    """Test message creation endpoint."""
    print("\n=== Testing Message Endpoint ===")
    
    mock_pipeline = create_mock_pipeline()
    with patch("fastapi_server.server_rest.pipeline", mock_pipeline):
        client = TestClient(app)
        auth_headers = {"Authorization": "Bearer test-key-1"}
        conv_id = "c_test123"
        
        # Test non-streaming message
        response = client.post(
            f"/v1/conversations/{conv_id}/messages",
            headers=auth_headers,
            json={
                "role": "user",
                "content": "Hello, how are you?",
                "stream": False
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data["conversation_id"] == conv_id, "Should return correct conversation_id"
        assert "message" in data, "Response should contain message"
        assert data["message"]["role"] == "assistant", "Message role should be assistant"
        assert "content" in data["message"], "Message should contain content"
        print("✓ Non-streaming message creation works")
        
        # Test streaming message
        response = client.post(
            f"/v1/conversations/{conv_id}/messages",
            headers=auth_headers,
            json={
                "role": "user",
                "content": "Hello",
                "stream": True
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "text/event-stream" in response.headers["content-type"], "Should return event-stream"
        print("✓ Streaming message creation works")
        
        # Test invalid role
        response = client.post(
            f"/v1/conversations/{conv_id}/messages",
            headers=auth_headers,
            json={
                "role": "assistant",
                "content": "Hello",
                "stream": False
            }
        )
        assert response.status_code == 400, f"Expected 400 for invalid role, got {response.status_code}"
        assert "Only role='user' is supported" in response.json()["detail"], "Should reject non-user role"
        print("✓ Invalid role rejection works")


def test_memory_deletion():
    """Test memory deletion endpoints."""
    print("\n=== Testing Memory Deletion ===")
    
    mock_pipeline = create_mock_pipeline()
    with patch("fastapi_server.server_rest.pipeline", mock_pipeline):
        client = TestClient(app)
        auth_headers = {"Authorization": "Bearer test-key-1"}
        
        # Test delete all memory
        response = client.delete("/v1/memory", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data["status"] == "success", "Should return success status"
        assert data["scope"] == "all", "Should indicate all scope"
        mock_pipeline.aclear_memory.assert_called_once()
        print("✓ Delete all memory works")
        
        # Test delete conversation memory
        conv_id = "c_test123"
        response = client.delete(
            f"/v1/conversations/{conv_id}/memory",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data["status"] == "success", "Should return success status"
        assert data["scope"] == "conversation", "Should indicate conversation scope"
        assert data["conversation_id"] == conv_id, "Should return conversation_id"
        mock_pipeline.graph.memory.delete_thread.assert_called()
        print("✓ Delete conversation memory works")
        
        # Test delete conversation memory with device_id format
        conv_id_with_device = "c_test123_device456"
        response = client.delete(
            f"/v1/conversations/{conv_id_with_device}/memory",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        # Should normalize to base thread_id
        mock_pipeline.graph.memory.delete_thread.assert_called_with("c_test123")
        print("✓ Delete conversation memory with device_id format works")
        
        # Test delete conversation memory when MemorySaver is not available
        mock_pipeline_no_mem = create_mock_pipeline()
        mock_pipeline_no_mem.graph.memory = None
        
        with patch("fastapi_server.server_rest.pipeline", mock_pipeline_no_mem):
            response = client.delete(
                f"/v1/conversations/{conv_id}/memory",
                headers=auth_headers
            )
            assert response.status_code == 501, f"Expected 501, got {response.status_code}"
            data = response.json()
            assert data["status"] == "unsupported", "Should return unsupported status"
            print("✓ Unsupported memory deletion handling works")


def test_error_handling():
    """Test error handling."""
    print("\n=== Testing Error Handling ===")
    
    with patch("fastapi_server.server_rest.pipeline", create_mock_pipeline()):
        client = TestClient(app)
        auth_headers = {"Authorization": "Bearer test-key-1"}
        
        # Test chat with missing input
        response = client.post(
            "/v1/chat",
            headers=auth_headers,
            json={"stream": False}
        )
        assert response.status_code == 422, f"Expected 422 for validation error, got {response.status_code}"
        print("✓ Missing input validation works")
        
        # Test message with missing content
        response = client.post(
            "/v1/conversations/c_test123/messages",
            headers=auth_headers,
            json={"role": "user", "stream": False}
        )
        assert response.status_code == 422, f"Expected 422 for validation error, got {response.status_code}"
        print("✓ Missing content validation works")


def run_all_tests():
    """Run all tests."""
    if not HAS_TEST_CLIENT:
        print("Cannot run tests: fastapi.testclient not available")
        print("Install with: pip install pytest httpx")
        return False
    
    print("=" * 60)
    print("Running REST API Tests")
    print("=" * 60)
    
    try:
        test_health_endpoints()
        test_authentication()
        test_conversation_creation()
        test_chat_endpoint()
        test_message_endpoint()
        test_memory_deletion()
        test_error_handling()
        
        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        return True
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)


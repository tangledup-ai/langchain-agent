#!/usr/bin/env python3
"""
Tests for the REST API server (server_rest.py)

This test suite covers:
- Health check endpoints (GET /, GET /health)
- API key authentication (valid/invalid keys, Bearer format)
- Conversation creation (POST /v1/conversations)
- Chat endpoint (POST /v1/chat) - streaming and non-streaming
- Message creation (POST /v1/conversations/{id}/messages) - streaming and non-streaming
- Memory deletion (DELETE /v1/memory, DELETE /v1/conversations/{id}/memory)
- Edge cases and error handling

Run with: pytest tests/test_server_rest.py -v
"""
import os
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

# Set up test environment before importing the server
os.environ["FAST_AUTH_KEYS"] = "test-key-1,test-key-2,test-key-3"

# Import after setting environment
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi_server.server_rest import app


@pytest.fixture
def mock_pipeline():
    """Create a mock Pipeline instance."""
    pipeline = MagicMock()
    
    # Mock async generator for streaming
    async def mock_achat_stream(inp, as_stream=True, thread_id="test"):
        chunks = ["Hello", " ", "world", "!"]
        for chunk in chunks:
            yield chunk
    
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


@pytest.fixture
def client(mock_pipeline):
    """Create a test client with mocked pipeline."""
    with patch("fastapi_server.server_rest.pipeline", mock_pipeline):
        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture
def auth_headers():
    """Return valid authentication headers."""
    return {"Authorization": "Bearer test-key-1"}


@pytest.fixture
def invalid_auth_headers():
    """Return invalid authentication headers."""
    return {"Authorization": "Bearer invalid-key"}


class TestHealthCheck:
    """Tests for health check endpoint."""
    
    def test_root_endpoint(self, client):
        """Test root endpoint returns API information."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "endpoints" in data
        assert isinstance(data["endpoints"], list)
    
    def test_health_endpoint(self, client):
        """Test health endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestAuthentication:
    """Tests for API key authentication."""
    
    def test_missing_auth_header(self, client):
        """Test that missing auth header returns 401."""
        response = client.post("/v1/conversations")
        assert response.status_code == 401
    
    def test_invalid_api_key(self, client, invalid_auth_headers):
        """Test that invalid API key returns 401."""
        response = client.post(
            "/v1/conversations",
            headers=invalid_auth_headers
        )
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]
    
    def test_valid_api_key_bearer_format(self, client, auth_headers):
        """Test that valid API key with Bearer prefix works."""
        response = client.post(
            "/v1/conversations",
            headers=auth_headers
        )
        assert response.status_code == 200
    
    def test_valid_api_key_without_bearer(self, client):
        """Test that valid API key without Bearer prefix works."""
        response = client.post(
            "/v1/conversations",
            headers={"Authorization": "test-key-1"}
        )
        assert response.status_code == 200
    
    def test_multiple_valid_keys(self, client):
        """Test that any of the configured keys work."""
        for key in ["test-key-1", "test-key-2", "test-key-3"]:
            response = client.post(
                "/v1/conversations",
                headers={"Authorization": f"Bearer {key}"}
            )
            assert response.status_code == 200


class TestConversationCreation:
    """Tests for conversation creation endpoint."""
    
    def test_create_conversation(self, client, auth_headers):
        """Test creating a new conversation."""
        response = client.post(
            "/v1/conversations",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "created_at" in data
        assert data["id"].startswith("c_")
        assert len(data["id"]) > 2
    
    def test_conversation_id_format(self, client, auth_headers):
        """Test that conversation IDs follow expected format."""
        response = client.post(
            "/v1/conversations",
            headers=auth_headers
        )
        data = response.json()
        conv_id = data["id"]
        # Should start with "c_" and have hex characters
        assert conv_id.startswith("c_")
        assert len(conv_id) > 2


class TestChatEndpoint:
    """Tests for the /v1/chat endpoint."""
    
    def test_chat_non_streaming(self, client, auth_headers, mock_pipeline):
        """Test non-streaming chat request."""
        with patch("fastapi_server.server_rest.pipeline", mock_pipeline):
            response = client.post(
                "/v1/chat",
                headers=auth_headers,
                json={
                    "input": "Hello, how are you?",
                    "stream": False
                }
            )
            assert response.status_code == 200
            data = response.json()
            assert "conversation_id" in data
            assert "output" in data
            assert data["output"] == "Hello world!"
            mock_pipeline.achat.assert_called_once()
            call_kwargs = mock_pipeline.achat.call_args.kwargs
            assert call_kwargs["inp"] == "Hello, how are you?"
            assert call_kwargs["as_stream"] is False
    
    def test_chat_with_existing_conversation_id(self, client, auth_headers, mock_pipeline):
        """Test chat with existing conversation ID."""
        with patch("fastapi_server.server_rest.pipeline", mock_pipeline):
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
            assert response.status_code == 200
            data = response.json()
            assert data["conversation_id"] == conv_id
            call_kwargs = mock_pipeline.achat.call_args.kwargs
            assert call_kwargs["thread_id"] == conv_id
    
    def test_chat_creates_new_conversation_id(self, client, auth_headers, mock_pipeline):
        """Test chat creates new conversation ID when not provided."""
        with patch("fastapi_server.server_rest.pipeline", mock_pipeline):
            response = client.post(
                "/v1/chat",
                headers=auth_headers,
                json={
                    "input": "Hello",
                    "stream": False
                }
            )
            assert response.status_code == 200
            data = response.json()
            assert "conversation_id" in data
            assert data["conversation_id"].startswith("c_")
    
    def test_chat_streaming(self, client, auth_headers, mock_pipeline):
        """Test streaming chat request."""
        with patch("fastapi_server.server_rest.pipeline", mock_pipeline):
            response = client.post(
                "/v1/chat",
                headers=auth_headers,
                json={
                    "input": "Hello",
                    "stream": True
                }
            )
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            
            # Read streaming response
            lines = response.text.split("\n")
            data_lines = [line for line in lines if line.startswith("data: ")]
            
            # Should have delta events and a done event
            assert len(data_lines) > 0
            
            # Parse first delta event
            first_data = json.loads(data_lines[0][6:])  # Remove "data: " prefix
            assert first_data["type"] == "delta"
            assert "conversation_id" in first_data
            assert "delta" in first_data
            
            # Check that achat was called with as_stream=True
            mock_pipeline.achat.assert_called_once()
            call_kwargs = mock_pipeline.achat.call_args.kwargs
            assert call_kwargs["as_stream"] is True


class TestMessageEndpoint:
    """Tests for the /v1/conversations/{conversation_id}/messages endpoint."""
    
    def test_create_message_non_streaming(self, client, auth_headers, mock_pipeline):
        """Test creating a message (non-streaming)."""
        with patch("fastapi_server.server_rest.pipeline", mock_pipeline):
            conv_id = "c_test123"
            response = client.post(
                f"/v1/conversations/{conv_id}/messages",
                headers=auth_headers,
                json={
                    "role": "user",
                    "content": "Hello, how are you?",
                    "stream": False
                }
            )
            assert response.status_code == 200
            data = response.json()
            assert data["conversation_id"] == conv_id
            assert "message" in data
            assert data["message"]["role"] == "assistant"
            assert "content" in data["message"]
            mock_pipeline.achat.assert_called_once()
            call_kwargs = mock_pipeline.achat.call_args.kwargs
            assert call_kwargs["inp"] == "Hello, how are you?"
            assert call_kwargs["thread_id"] == conv_id
    
    def test_create_message_streaming(self, client, auth_headers, mock_pipeline):
        """Test creating a message (streaming)."""
        with patch("fastapi_server.server_rest.pipeline", mock_pipeline):
            conv_id = "c_test123"
            response = client.post(
                f"/v1/conversations/{conv_id}/messages",
                headers=auth_headers,
                json={
                    "role": "user",
                    "content": "Hello",
                    "stream": True
                }
            )
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            
            # Verify achat was called with streaming
            mock_pipeline.achat.assert_called_once()
            call_kwargs = mock_pipeline.achat.call_args.kwargs
            assert call_kwargs["as_stream"] is True
            assert call_kwargs["thread_id"] == conv_id
    
    def test_create_message_invalid_role(self, client, auth_headers):
        """Test that only 'user' role is accepted."""
        conv_id = "c_test123"
        response = client.post(
            f"/v1/conversations/{conv_id}/messages",
            headers=auth_headers,
            json={
                "role": "assistant",
                "content": "Hello",
                "stream": False
            }
        )
        assert response.status_code == 400
        assert "Only role='user' is supported" in response.json()["detail"]


class TestMemoryDeletion:
    """Tests for memory deletion endpoints."""
    
    def test_delete_all_memory(self, client, auth_headers, mock_pipeline):
        """Test deleting all memory."""
        with patch("fastapi_server.server_rest.pipeline", mock_pipeline):
            response = client.delete(
                "/v1/memory",
                headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["scope"] == "all"
            mock_pipeline.aclear_memory.assert_called_once()
    
    def test_delete_all_memory_error_handling(self, client, auth_headers, mock_pipeline):
        """Test error handling when deleting all memory fails."""
        mock_pipeline.aclear_memory = AsyncMock(side_effect=Exception("Memory error"))
        
        with patch("fastapi_server.server_rest.pipeline", mock_pipeline):
            response = client.delete(
                "/v1/memory",
                headers=auth_headers
            )
            assert response.status_code == 500
            assert "Memory error" in response.json()["detail"]
    
    def test_delete_conversation_memory(self, client, auth_headers, mock_pipeline):
        """Test deleting memory for a specific conversation."""
        conv_id = "c_test123"
        
        with patch("fastapi_server.server_rest.pipeline", mock_pipeline):
            response = client.delete(
                f"/v1/conversations/{conv_id}/memory",
                headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["scope"] == "conversation"
            assert data["conversation_id"] == conv_id
            # Verify delete_thread was called
            mock_pipeline.graph.memory.delete_thread.assert_called_once()
    
    def test_delete_conversation_memory_with_device_id(self, client, auth_headers, mock_pipeline):
        """Test deleting memory for conversation with device ID format."""
        conv_id = "c_test123_device456"
        
        with patch("fastapi_server.server_rest.pipeline", mock_pipeline):
            response = client.delete(
                f"/v1/conversations/{conv_id}/memory",
                headers=auth_headers
            )
            assert response.status_code == 200
            # Should normalize to base thread_id
            mock_pipeline.graph.memory.delete_thread.assert_called_once_with("c_test123")
    
    def test_delete_conversation_memory_no_memory_saver(self, client, auth_headers):
        """Test deleting conversation memory when MemorySaver is not available."""
        # Create a mock pipeline without MemorySaver
        mock_pipeline_no_mem = MagicMock()
        mock_pipeline_no_mem.graph = MagicMock()
        mock_pipeline_no_mem.graph.memory = None
        
        with patch("fastapi_server.server_rest.pipeline", mock_pipeline_no_mem):
            conv_id = "c_test123"
            response = client.delete(
                f"/v1/conversations/{conv_id}/memory",
                headers=auth_headers
            )
            assert response.status_code == 501
            data = response.json()
            assert data["status"] == "unsupported"
            assert "not supported" in data["message"].lower()


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_chat_empty_input(self, client, auth_headers, mock_pipeline):
        """Test chat with empty input."""
        with patch("fastapi_server.server_rest.pipeline", mock_pipeline):
            response = client.post(
                "/v1/chat",
                headers=auth_headers,
                json={
                    "input": "",
                    "stream": False
                }
            )
            # Should still process (validation would be in Pipeline)
            assert response.status_code in [200, 400]
    
    def test_chat_missing_input(self, client, auth_headers):
        """Test chat with missing input field."""
        response = client.post(
            "/v1/chat",
            headers=auth_headers,
            json={
                "stream": False
            }
        )
        assert response.status_code == 422  # Validation error
    
    def test_message_missing_content(self, client, auth_headers):
        """Test message creation with missing content."""
        conv_id = "c_test123"
        response = client.post(
            f"/v1/conversations/{conv_id}/messages",
            headers=auth_headers,
            json={
                "role": "user",
                "stream": False
            }
        )
        assert response.status_code == 422  # Validation error
    
    def test_invalid_conversation_id_format(self, client, auth_headers, mock_pipeline):
        """Test that various conversation ID formats are handled."""
        with patch("fastapi_server.server_rest.pipeline", mock_pipeline):
            # Test with underscore (device_id format)
            conv_id = "thread_123_device_456"
            response = client.post(
                f"/v1/conversations/{conv_id}/messages",
                headers=auth_headers,
                json={
                    "role": "user",
                    "content": "Hello",
                    "stream": False
                }
            )
            # Should normalize thread_id (take first part before _)
            assert response.status_code == 200
            call_kwargs = mock_pipeline.achat.call_args.kwargs
            # The thread_id normalization happens in _normalize_thread_id
            # but achat receives the full conversation_id
            assert call_kwargs["thread_id"] == conv_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


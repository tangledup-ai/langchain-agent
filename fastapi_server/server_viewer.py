from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Optional
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Ensure we can import from project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lang_agent.components.conv_store import ConversationStore

app = FastAPI(
    title="Conversation Viewer",
    description="Web UI to view conversations from the database",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize conversation store
try:
    conv_store = ConversationStore()
except ValueError as e:
    print(f"Warning: {e}. Make sure CONN_STR environment variable is set.")
    conv_store = None


class MessageResponse(BaseModel):
    message_type: str
    content: str
    sequence_number: int
    created_at: str


class ConversationListItem(BaseModel):
    conversation_id: str
    message_count: int
    last_updated: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main HTML page"""
    html_path = Path(__file__).parent.parent / "static" / "viewer.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    else:
        return HTMLResponse(content="<h1>Viewer HTML not found. Please create static/viewer.html</h1>")


@app.get("/api/conversations", response_model=List[ConversationListItem])
async def list_conversations():
    """Get list of all conversations"""
    if conv_store is None:
        raise HTTPException(status_code=500, detail="Database connection not configured")
    
    import psycopg
    conn_str = os.environ.get("CONN_STR")
    if not conn_str:
        raise HTTPException(status_code=500, detail="CONN_STR not set")
    
    with psycopg.connect(conn_str) as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            # Get all unique conversation IDs with message counts and last updated time
            cur.execute("""
                SELECT 
                    conversation_id,
                    COUNT(*) as message_count,
                    MAX(created_at) as last_updated
                FROM messages
                GROUP BY conversation_id
                ORDER BY last_updated DESC
            """)
            results = cur.fetchall()
            
            return [
                ConversationListItem(
                    conversation_id=row["conversation_id"],
                    message_count=row["message_count"],
                    last_updated=row["last_updated"].isoformat() if row["last_updated"] else None
                )
                for row in results
            ]


@app.get("/api/conversations/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_conversation_messages(conversation_id: str):
    """Get all messages for a specific conversation"""
    if conv_store is None:
        raise HTTPException(status_code=500, detail="Database connection not configured")
    
    messages = conv_store.get_conversation(conversation_id)
    
    return [
        MessageResponse(
            message_type=msg["message_type"],
            content=msg["content"],
            sequence_number=msg["sequence_number"],
            created_at=msg["created_at"].isoformat() if msg["created_at"] else ""
        )
        for msg in messages
    ]


@app.get("/health")
async def health():
    return {"status": "healthy", "db_connected": conv_store is not None}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server_viewer:app",
        host="0.0.0.0",
        port=8590,
        reload=True,
    )


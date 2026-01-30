import psycopg
from uuid import UUID
from typing import List, Dict, Union
from enum import Enum
import os

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage

class MessageType(str, Enum):
    """Enum for message types in the conversation store."""
    HUMAN = "human"
    AI = "ai"
    TOOL = "tool"

class ConversationStore:
    def __init__(self):
        conn_str = os.environ.get("CONN_STR")
        if conn_str is None:
            raise ValueError("CONN_STR is not set")
        self.conn_str = conn_str

    def _coerce_conversation_id(self, conversation_id: Union[str, UUID]) -> UUID:
        if isinstance(conversation_id, UUID):
            return conversation_id
        try:
            return UUID(conversation_id)
        except (TypeError, ValueError) as e:
            raise ValueError("conversation_id must be a UUID (or UUID string)") from e
    
    def add_message(
        self,
        conversation_id: Union[str, UUID],
        msg_type: MessageType,
        content: str,
        sequence: int,   # the conversation number
    ):
        conversation_id = self._coerce_conversation_id(conversation_id)
        with psycopg.connect(self.conn_str) as conn:
            with conn.cursor() as cur:
                # DB schema only supports these columns:
                # (conversation_id, message_type, content, sequence_number)
                cur.execute(
                    """
                    INSERT INTO messages (conversation_id, message_type, content, sequence_number)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (conversation_id, msg_type.value, content, sequence),
                )
    
    def get_conv_number(self, conversation_id: Union[str, UUID]) -> int:
        """
            if the conversation_id does not exist, return 0
            if len(conversation) = 3, it will return 3
        """
        conversation_id = self._coerce_conversation_id(conversation_id)
        with psycopg.connect(self.conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*)
                    FROM messages
                    WHERE conversation_id = %s
                    """, (conversation_id,))
                return int(cur.fetchone()[0])
    
    def get_conversation(self, conversation_id: Union[str, UUID]) -> List[Dict]:
        conversation_id = self._coerce_conversation_id(conversation_id)
        with psycopg.connect(self.conn_str) as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute("""
                    SELECT message_type, content, sequence_number, created_at
                    FROM messages
                    WHERE conversation_id = %s
                    ORDER BY sequence_number ASC
                """, (conversation_id,))
                return cur.fetchall()
    
    def record_messages(self, conv_id:str, inp:List[BaseMessage]):
        curr_len = self.get_conv_number(conv_id)
        to_add_msg = inp[curr_len:]
        for msg in to_add_msg:
            self.add_message(conv_id, self._get_type(msg), msg.content, curr_len + 1)
            curr_len += 1
        return curr_len
    
    
    def _get_type(self, msg:BaseMessage) -> MessageType:
        if isinstance(msg, HumanMessage):
            return MessageType.HUMAN
        elif isinstance(msg, AIMessage):
            return MessageType.AI
        elif isinstance(msg, ToolMessage):
            return MessageType.TOOL
        else:
            raise ValueError(f"Unknown message type: {type(msg)}")

CONV_STORE = ConversationStore()
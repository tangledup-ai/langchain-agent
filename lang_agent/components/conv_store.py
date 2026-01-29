import psycopg
from uuid import UUID
from typing import List, Dict, Literal, Union
import os

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
        msg_type: Literal["human", "ai", "tool"],
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
                    (conversation_id, msg_type, content, sequence),
                )
    
    def get_conv_number(self, conversation_id: Union[str, UUID]) -> int:
        conversation_id = self._coerce_conversation_id(conversation_id)
        with psycopg.connect(self.conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COALESCE(MAX(sequence_number), -1)
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


CONV_STORE = ConversationStore()
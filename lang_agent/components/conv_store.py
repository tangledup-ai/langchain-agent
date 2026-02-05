import json
import psycopg
from typing import List, Dict, Union
from enum import Enum
import os

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage, BaseMessage

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

    def add_message(
        self,
        conversation_id: str,
        msg_type: MessageType,
        content: str,
        sequence: int,   # the conversation number
    ):
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
    
    def get_conv_number(self, conversation_id: str) -> int:
        """
            if the conversation_id does not exist, return 0
            if len(conversation) = 3, it will return 3
        """
        with psycopg.connect(self.conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*)
                    FROM messages
                    WHERE conversation_id = %s
                    """, (conversation_id,))
                return int(cur.fetchone()[0])
    
    def get_conversation(self, conversation_id: str) -> List[Dict]:
        with psycopg.connect(self.conn_str) as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute("""
                    SELECT message_type, content, sequence_number, created_at
                    FROM messages
                    WHERE conversation_id = %s
                    ORDER BY sequence_number ASC
                """, (conversation_id,))
                return cur.fetchall()
    
    def record_message_list(self, conv_id:str, inp:List[BaseMessage]):
        inp = [e for e in inp if not isinstance(e, SystemMessage)]
        curr_len = self.get_conv_number(conv_id)
        to_add_msg = inp[curr_len:]
        for msg in to_add_msg:
            content = msg.content
            # Serialize dict/list content to JSON string
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False, indent=4)
            self.add_message(conv_id, self._get_type(msg), content, curr_len + 1)
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


class ConversationPrinter:
    def __init__(self):
        self.id_dic = {}
    
    def record_message_list(self, conv_id:str, inp:List[BaseMessage]):
        inp = [e for e in inp if not isinstance(e, SystemMessage)]
        curr_len = self.id_dic.get(conv_id, 0)
        to_print_msg = inp[curr_len:]
        for msg in to_print_msg:
            msg.pretty_print()
        
        if curr_len == 0:
            self.id_dic[conv_id] = len(inp)
        else:
            self.id_dic[conv_id] += len(to_print_msg)
 
CONV_STORE = ConversationStore()
# CONV_STORE = ConversationPrinter()
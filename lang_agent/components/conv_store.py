import json
import hashlib
import os
from typing import List, Dict, Optional
from enum import Enum
from loguru import logger
from abc import ABC, abstractmethod

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    ToolMessage,
    SystemMessage,
    BaseMessage,
)
from psycopg.rows import dict_row

from lang_agent.components.db_pool import db_connection
from lang_agent.components.runtime_services import get_runtime_services


class MessageType(str, Enum):
    """Enum for message types in the conversation store."""

    HUMAN = "human"
    AI = "ai"
    TOOL = "tool"


class BaseConvStore(ABC):
    @abstractmethod
    def record_message_list(
        self, conv_id: str, inp: List[BaseMessage], pipeline_id: str = None
    ):
        pass


class ConversationStore(BaseConvStore):
    def __init__(self, conn_str: Optional[str] = None):
        self.conn_str = conn_str or os.environ.get("CONN_STR")
        if self.conn_str is None:
            raise ValueError("CONN_STR is not set")

    def _conversation_lock_id(self, conversation_id: str) -> int:
        digest = hashlib.sha256(conversation_id.encode("utf-8")).digest()
        # pg_advisory_xact_lock expects bigint; use a signed 64-bit value.
        return int.from_bytes(digest[:8], byteorder="big", signed=True)

    def add_message(
        self,
        conversation_id: str,
        msg_type: MessageType,
        content: str,
        sequence: int,
        pipeline_id: str = None,
    ):
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO messages (conversation_id, pipeline_id, message_type, content, sequence_number)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (conversation_id, pipeline_id, msg_type.value, content, sequence),
                )
            conn.commit()

    def get_conv_number(self, conversation_id: str) -> int:
        """
        if the conversation_id does not exist, return 0
        if len(conversation) = 3, it will return 3
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(MAX(sequence_number), 0)
                    FROM messages
                    WHERE conversation_id = %s
                    """,
                    (conversation_id,),
                )
                return int(cur.fetchone()[0])

    def get_conversation(self, conversation_id: str) -> List[Dict]:
        with db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT message_type, content, sequence_number, created_at
                    FROM messages
                    WHERE conversation_id = %s
                    ORDER BY sequence_number ASC
                """,
                    (conversation_id,),
                )
                return cur.fetchall()

    def _serialize_messages(self, inp: List[BaseMessage]) -> List[Dict[str, object]]:
        serialized: List[Dict[str, object]] = []
        for msg in inp:
            content = msg.content
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False, indent=4)
            serialized.append(
                {
                    "type": self._get_type(msg),
                    "content": content,
                }
            )
        return serialized

    def record_message_list(
        self, conv_id: str, inp: List[BaseMessage], pipeline_id: str = None
    ):
        inp = [e for e in inp if not isinstance(e, SystemMessage)]
        serialized = self._serialize_messages(inp)

        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_advisory_xact_lock(%s::bigint)",
                    (self._conversation_lock_id(conv_id),),
                )
                cur.execute(
                    """
                    SELECT COALESCE(MAX(sequence_number), 0)
                    FROM messages
                    WHERE conversation_id = %s
                    """,
                    (conv_id,),
                )
                curr_len = int(cur.fetchone()[0])
                to_add_msg = serialized[curr_len:]

                if to_add_msg:
                    cur.executemany(
                        """
                        INSERT INTO messages (
                            conversation_id,
                            pipeline_id,
                            message_type,
                            content,
                            sequence_number
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        [
                            (
                                conv_id,
                                pipeline_id,
                                msg["type"].value,
                                msg["content"],
                                curr_len + index + 1,
                            )
                            for index, msg in enumerate(to_add_msg)
                        ],
                    )
                    conn.commit()
                    self._publish_conversation_updated(
                        conversation_id=conv_id,
                        pipeline_id=pipeline_id,
                        message_count=curr_len + len(to_add_msg),
                    )
                return curr_len + len(to_add_msg)

    def _publish_conversation_updated(
        self,
        conversation_id: str,
        pipeline_id: Optional[str],
        message_count: int,
    ) -> None:
        services = get_runtime_services()
        services.cache.delete(
            services.cache.conversation_messages_key(
                pipeline_id or "default", conversation_id
            )
        )
        if pipeline_id:
            for limit in (50, 100, 500):
                services.cache.delete(
                    services.cache.conversation_list_key(pipeline_id, limit)
                )
        services.message_bus.publish(
            "conversation.updated",
            {
                "conversation_id": conversation_id,
                "pipeline_id": pipeline_id,
                "message_count": message_count,
            },
        )

    def _get_type(self, msg: BaseMessage) -> MessageType:
        if isinstance(msg, HumanMessage):
            return MessageType.HUMAN
        elif isinstance(msg, AIMessage):
            return MessageType.AI
        elif isinstance(msg, ToolMessage):
            return MessageType.TOOL
        else:
            raise ValueError(f"Unknown message type: {type(msg)}")


class ConversationPrinter(BaseConvStore):
    def __init__(self):
        self.id_dic = {}

    def record_message_list(
        self, conv_id: str, inp: List[BaseMessage], pipeline_id: str = None
    ):
        inp = [e for e in inp if not isinstance(e, SystemMessage)]
        curr_len = self.id_dic.get(conv_id, 0)
        to_print_msg = inp[curr_len:]
        print("\n")
        for msg in to_print_msg:
            msg.pretty_print()

        if curr_len == 0:
            self.id_dic[conv_id] = len(inp)
        else:
            self.id_dic[conv_id] += len(to_print_msg)


class _ConversationStoreProxy(BaseConvStore):
    def record_message_list(
        self, conv_id: str, inp: List[BaseMessage], pipeline_id: str = None
    ):
        return get_conv_store().record_message_list(
            conv_id, inp, pipeline_id=pipeline_id
        )

    def __getattr__(self, item):
        return getattr(get_conv_store(), item)


_CONV_STORE_OVERRIDE: Optional[BaseConvStore] = None
_CONV_STORE_SINGLETON: Optional[ConversationStore] = None
CONV_STORE = _ConversationStoreProxy()
# _CONV_STORE_OVERRIDE = ConversationPrinter()


def use_printer():
    global _CONV_STORE_OVERRIDE
    _CONV_STORE_OVERRIDE = ConversationPrinter()


def use_database_store():
    global _CONV_STORE_OVERRIDE
    _CONV_STORE_OVERRIDE = None


def get_conv_store(required: bool = True) -> BaseConvStore:
    global _CONV_STORE_SINGLETON
    if _CONV_STORE_OVERRIDE is not None:
        return _CONV_STORE_OVERRIDE
    if _CONV_STORE_SINGLETON is None:
        if not os.environ.get("CONN_STR") and not required:
            return ConversationPrinter()
        _CONV_STORE_SINGLETON = ConversationStore()
    return _CONV_STORE_SINGLETON


def print_store_type():
    logger.info(get_conv_store(required=False))

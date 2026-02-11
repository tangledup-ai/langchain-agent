import os
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import psycopg
from psycopg.rows import dict_row


class DBConfigManager:
    def __init__(self):
        self.conn_str = os.environ.get("CONN_STR")
        if self.conn_str is None:
            raise ValueError("CONN_STR is not set")
    
    def remove_config(self, pipeline_id: str, prompt_set_id:str):
        with psycopg.connect(self.conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM prompt_sets WHERE pipeline_id = %s AND id = %s", (pipeline_id, prompt_set_id))
                conn.commit()

    def list_prompt_sets(
        self, pipeline_id: Optional[str] = None, graph_id: Optional[str] = None
    ) -> List[Dict[str, object]]:
        """
        List prompt_set metadata for UI listing.
        """
        with psycopg.connect(self.conn_str) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if pipeline_id and graph_id:
                    cur.execute(
                        """
                        SELECT id, pipeline_id, graph_id, name, description, is_active, created_at, updated_at, list
                        FROM prompt_sets
                        WHERE pipeline_id = %s AND graph_id = %s
                        ORDER BY updated_at DESC, created_at DESC
                        """,
                        (pipeline_id, graph_id),
                    )
                elif pipeline_id:
                    cur.execute(
                        """
                        SELECT id, pipeline_id, graph_id, name, description, is_active, created_at, updated_at, list
                        FROM prompt_sets
                        WHERE pipeline_id = %s
                        ORDER BY updated_at DESC, created_at DESC
                        """,
                        (pipeline_id,),
                    )
                elif graph_id:
                    cur.execute(
                        """
                        SELECT id, pipeline_id, graph_id, name, description, is_active, created_at, updated_at, list
                        FROM prompt_sets
                        WHERE graph_id = %s
                        ORDER BY updated_at DESC, created_at DESC
                        """,
                        (graph_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, pipeline_id, graph_id, name, description, is_active, created_at, updated_at, list
                        FROM prompt_sets
                        ORDER BY updated_at DESC, created_at DESC
                        """
                    )
                rows = cur.fetchall()

        return [
            {
                "prompt_set_id": str(row["id"]),
                "pipeline_id": row["pipeline_id"],
                "graph_id": row.get("graph_id"),
                "name": row["name"],
                "description": row["description"] or "",
                "is_active": bool(row["is_active"]),
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                "tool_keys": self._parse_tool_list(row.get("list")),
            }
            for row in rows
        ]

    def get_prompt_set(self, pipeline_id: str, prompt_set_id: str) -> Optional[Dict[str, object]]:
        """
        Return prompt_set metadata by id within a pipeline.
        """
        with psycopg.connect(self.conn_str) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, pipeline_id, graph_id, name, description, is_active, created_at, updated_at, list
                    FROM prompt_sets
                    WHERE id = %s AND pipeline_id = %s
                    """,
                    (prompt_set_id, pipeline_id),
                )
                row = cur.fetchone()

        if row is None:
            return None

        return {
            "prompt_set_id": str(row["id"]),
            "pipeline_id": row["pipeline_id"],
            "graph_id": row.get("graph_id"),
            "name": row["name"],
            "description": row["description"] or "",
            "is_active": bool(row["is_active"]),
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            "tool_keys": self._parse_tool_list(row.get("list")),
        }

    def get_config(
        self, pipeline_id: str, prompt_set_id: Optional[str] = None
    ) -> Tuple[Dict[str, str], List[str]]:
        """
        Read prompt + tool configuration from DB.

        Returns:
            ({prompt_key: content}, [tool_key, ...])

        Resolution order:
            - If prompt_set_id is provided, read that set.
            - Otherwise, read the active set for pipeline_id.
            - If no matching set exists, return ({}, []).
        """
        if not pipeline_id:
            raise ValueError("pipeline_id is required")

        with psycopg.connect(self.conn_str) as conn:
            resolved_set_id, tool_csv = self._resolve_prompt_set(
                conn,
                pipeline_id=pipeline_id,
                graph_id=None,
                prompt_set_id=prompt_set_id,
                create_if_missing=False,
            )
            if resolved_set_id is None:
                return {}, []

            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT prompt_key, content
                    FROM prompt_templates
                    WHERE prompt_set_id = %s
                    """,
                    (resolved_set_id,),
                )
                rows = cur.fetchall()

        prompt_dict: Dict[str, str] = {row["prompt_key"]: row["content"] for row in rows}
        return prompt_dict, self._parse_tool_list(tool_csv)

    def set_config(
        self,
        pipeline_id: str,
        graph_id: Optional[str],
        prompt_set_id: Optional[str],
        tool_list: Optional[Sequence[str]],
        prompt_dict: Optional[Mapping[str, str]],
    ) -> str:
        """
        Persist prompt + tool configuration.

        Behavior:
            - If prompt_set_id is provided, update that set (must belong to pipeline_id).
            - If prompt_set_id is None, update the active set for pipeline_id;
              create one if missing.
            - prompt_templates for the set are synchronized to prompt_dict
              (keys not present in prompt_dict are removed).

        Returns:
            The target prompt_set_id used for the write.
        """
        if not pipeline_id:
            raise ValueError("pipeline_id is required")
        normalized_graph_id = self._normalize_graph_id(graph_id)
        if prompt_set_id is None and not normalized_graph_id:
            raise ValueError("graph_id is required when creating a new prompt set")

        normalized_prompt_dict = self._normalize_prompt_dict(prompt_dict)
        tool_csv = self._join_tool_list(tool_list)

        with psycopg.connect(self.conn_str) as conn:
            resolved_set_id, _ = self._resolve_prompt_set(
                conn,
                pipeline_id=pipeline_id,
                graph_id=normalized_graph_id,
                prompt_set_id=prompt_set_id,
                create_if_missing=prompt_set_id is None,
            )
            if resolved_set_id is None:
                raise ValueError(
                    f"prompt_set_id '{prompt_set_id}' not found for pipeline '{pipeline_id}'"
                )

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE prompt_sets
                    SET list = %s, graph_id = COALESCE(%s, graph_id), updated_at = now()
                    WHERE id = %s
                    """,
                    (tool_csv, normalized_graph_id, resolved_set_id),
                )

                keys = list(normalized_prompt_dict.keys())
                if keys:
                    cur.execute(
                        """
                        DELETE FROM prompt_templates
                        WHERE prompt_set_id = %s
                          AND NOT (prompt_key = ANY(%s))
                        """,
                        (resolved_set_id, keys),
                    )
                else:
                    cur.execute(
                        """
                        DELETE FROM prompt_templates
                        WHERE prompt_set_id = %s
                        """,
                        (resolved_set_id,),
                    )

                if normalized_prompt_dict:
                    cur.executemany(
                        """
                        INSERT INTO prompt_templates (prompt_set_id, prompt_key, content)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (prompt_set_id, prompt_key)
                        DO UPDATE SET
                            content = EXCLUDED.content,
                            updated_at = now()
                        """,
                        [
                            (resolved_set_id, prompt_key, content)
                            for prompt_key, content in normalized_prompt_dict.items()
                        ],
                    )

            conn.commit()
            return str(resolved_set_id)

    def _resolve_prompt_set(
        self,
        conn: psycopg.Connection,
        pipeline_id: str,
        graph_id: Optional[str],
        prompt_set_id: Optional[str],
        create_if_missing: bool,
    ) -> Tuple[Optional[str], str]:
        """
        Resolve target prompt_set and return (id, list_csv).
        """
        with conn.cursor(row_factory=dict_row) as cur:
            if prompt_set_id:
                cur.execute(
                    """
                    SELECT id, list
                    FROM prompt_sets
                    WHERE id = %s AND pipeline_id = %s
                    """,
                    (prompt_set_id, pipeline_id),
                )
            else:
                cur.execute(
                    """
                    SELECT id, list
                    FROM prompt_sets
                    WHERE pipeline_id = %s AND is_active = true
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT 1
                    """,
                    (pipeline_id,),
                )

            row = cur.fetchone()
            if row is not None:
                return str(row["id"]), row.get("list") or ""

            if not create_if_missing:
                return None, ""

            cur.execute(
                """
                INSERT INTO prompt_sets (pipeline_id, graph_id, name, description, is_active, list)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, list
                """,
                (
                    pipeline_id,
                    graph_id,
                    "default",
                    "Auto-created by DBConfigManager",
                    True,
                    "",
                ),
            )
            created = cur.fetchone()
            return str(created["id"]), created.get("list") or ""

    def _join_tool_list(self, tool_list: Optional[Sequence[str]]) -> str:
        if not tool_list:
            return ""
        cleaned: List[str] = []
        seen = set()
        for tool in tool_list:
            if tool is None:
                continue
            key = str(tool).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            cleaned.append(key)
        return ",".join(cleaned)

    def _parse_tool_list(self, tool_csv: Optional[str]) -> List[str]:
        if not tool_csv:
            return []
        return [k.strip() for k in tool_csv.split(",") if k.strip()]

    def _normalize_prompt_dict(
        self, prompt_dict: Optional[Mapping[str, str]]
    ) -> Dict[str, str]:
        if not prompt_dict:
            return {}

        out: Dict[str, str] = {}
        for key, value in prompt_dict.items():
            norm_key = str(key).strip()
            if not norm_key:
                continue
            out[norm_key] = value if isinstance(value, str) else str(value)
        return out

    def _normalize_graph_id(self, graph_id: Optional[str]) -> Optional[str]:
        if graph_id is None:
            return None
        value = str(graph_id).strip()
        return value or None
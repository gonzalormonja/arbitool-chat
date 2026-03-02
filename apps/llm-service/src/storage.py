"""
PostgreSQL: read unprocessed messages, write trades, mark messages as processed.
"""
import os
import json
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgres://arbitool:arbitool@localhost:5432/arbitool_chat",
)


@contextmanager
def get_conn():
    with psycopg.connect(_DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


def fetch_unprocessed_messages(
    group_id: int,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Return messages with processed_at IS NULL in the given range."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    m.id, 
                    m.group_id, 
                    m.content, 
                    m.message_type, 
                    m.media_path, 
                    m.message_date,
                    p.display_name as sender_name
                FROM messages m
                LEFT JOIN participants p ON m.sender_id = p.id
                WHERE m.group_id = %s AND m.processed_at IS NULL
                  AND m.message_date >= COALESCE(%s::timestamptz, '-infinity'::timestamptz)
                  AND m.message_date <= COALESCE(%s::timestamptz, 'infinity'::timestamptz)
                ORDER BY m.message_date
                LIMIT %s
                """,
                (group_id, from_date, to_date, limit),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]


def insert_trade(
    group_id: int,
    trade_type: str,
    amount: float | None,
    currency: str | None,
    price_or_ref: str | None,
    message_ids: list[int],
    comprobante_media_path: str | None,
    raw_llm_response: dict | None,
) -> int:
    """Insert a trade and return its id."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trades (
                    group_id, type, amount, currency, price_or_ref,
                    message_ids, comprobante_media_path, raw_llm_response
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    group_id,
                    trade_type,
                    amount,
                    currency,
                    price_or_ref,
                    message_ids,
                    comprobante_media_path,
                    json.dumps(raw_llm_response) if raw_llm_response else None,
                ),
            )
            trade_id = cur.fetchone()["id"]
        conn.commit() # Important!
        return trade_id


def mark_messages_processed(message_ids: list[int]) -> None:
    """Set processed_at = NOW() for the given message ids."""
    if not message_ids:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE messages SET processed_at = NOW() WHERE id = ANY(%s)",
                (message_ids,),
            )
        conn.commit()

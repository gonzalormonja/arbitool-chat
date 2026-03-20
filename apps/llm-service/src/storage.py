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


def fetch_messages_with_overlap(
    group_id: int,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 100,
    overlap: int = 15,
) -> list[dict]:
    """
    Fetch unprocessed messages PLUS the last `overlap` processed messages before them.
    This allows the LLM to see context from the previous batch to avoid splitting operations.
    Each message dict has `_already_processed` = True/False so we know which to mark later.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH first_unprocessed AS (
                    SELECT MIN(message_date) as min_date
                    FROM messages
                    WHERE group_id = %s AND processed_at IS NULL
                      AND message_date >= COALESCE(%s::timestamptz, '-infinity'::timestamptz)
                      AND message_date <= COALESCE(%s::timestamptz, 'infinity'::timestamptz)
                ),
                overlap_messages AS (
                    SELECT m.id, m.group_id, m.content, m.message_type, m.media_path, 
                           m.message_date, p.display_name as sender_name,
                           TRUE as _already_processed
                    FROM messages m
                    LEFT JOIN participants p ON m.sender_id = p.id
                    WHERE m.group_id = %s 
                      AND m.processed_at IS NOT NULL
                      AND m.message_date < (SELECT min_date FROM first_unprocessed)
                    ORDER BY m.message_date DESC
                    LIMIT %s
                ),
                new_messages AS (
                    SELECT m.id, m.group_id, m.content, m.message_type, m.media_path,
                           m.message_date, p.display_name as sender_name,
                           FALSE as _already_processed
                    FROM messages m
                    LEFT JOIN participants p ON m.sender_id = p.id
                    WHERE m.group_id = %s AND m.processed_at IS NULL
                      AND m.message_date >= COALESCE(%s::timestamptz, '-infinity'::timestamptz)
                      AND m.message_date <= COALESCE(%s::timestamptz, 'infinity'::timestamptz)
                    ORDER BY m.message_date
                    LIMIT %s
                )
                SELECT * FROM overlap_messages
                UNION ALL
                SELECT * FROM new_messages
                ORDER BY message_date
                """,
                (group_id, from_date, to_date, group_id, overlap, group_id, from_date, to_date, limit),
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
    trade_date: str | None = None,
    *,
    bank: str | None = None,
    sender_name: str | None = None,
    cbu: str | None = None,
    transaction_id: str | None = None,
    id_colesa: str | None = None,
    comprobante_extra: str | None = None,
) -> int:
    """Insert a trade and return its id."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trades (
                    group_id, type, amount, currency, price_or_ref,
                    message_ids, comprobante_media_path, raw_llm_response, trade_date,
                    bank, sender_name, cbu, transaction_id, id_colesa, comprobante_extra
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    trade_date,
                    bank,
                    sender_name,
                    cbu,
                    transaction_id,
                    id_colesa,
                    comprobante_extra,
                ),
            )
            trade_id = cur.fetchone()["id"]
        conn.commit()
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

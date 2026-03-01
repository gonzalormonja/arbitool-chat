"""
LLM worker: consume jobs from Redis (arbitool:llm:jobs), fetch messages from PG,
call LLM to extract trades, write trades and mark messages as processed.
"""
import os
import json
import time
import signal
import sys

import redis

from . import client as llm_client
from . import storage as db

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_LLM_QUEUE_KEY = "arbitool:llm:jobs"
BATCH_SIZE = int(os.environ.get("LLM_BATCH_SIZE", "50"))
POLL_TIMEOUT = int(os.environ.get("LLM_POLL_TIMEOUT", "30"))
_shutdown = False


def handle_signal(_signum, _frame):
    global _shutdown
    _shutdown = True


def process_job(payload: dict) -> None:
    group_id = payload["group_id"]
    from_date = payload.get("from_date")
    to_date = payload.get("to_date")

    messages = db.fetch_unprocessed_messages(
        group_id=group_id,
        from_date=from_date,
        to_date=to_date,
        limit=BATCH_SIZE,
    )
    if not messages:
        return

    trades = llm_client.extract_trades_from_messages(messages)
    message_ids_used = set()
    for t in trades:
        msg_ids = t.get("message_ids") or []
        message_ids_used.update(msg_ids)
        db.insert_trade(
            group_id=group_id,
            trade_type=t.get("type", "buy"),
            amount=t.get("amount"),
            currency=t.get("currency"),
            price_or_ref=t.get("price_or_ref"),
            message_ids=msg_ids,
            comprobante_media_path=t.get("comprobante_media_path"),
            raw_llm_response=t,
        )

    if message_ids_used:
        db.mark_messages_processed(list(message_ids_used))


def run():
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

    print("LLM worker started, waiting for jobs...", file=sys.stderr)
    while not _shutdown:
        try:
            result = r.brpop(REDIS_LLM_QUEUE_KEY, timeout=POLL_TIMEOUT)
            if result is None:
                continue
            _key, value = result
            payload = json.loads(value)
            try:
                process_job(payload)
            except Exception as e:
                print(f"Job failed: {e}", file=sys.stderr)
                # Re-queue or log; for now we just skip
        except redis.ConnectionError as e:
            print(f"Redis error: {e}", file=sys.stderr)
            time.sleep(5)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            time.sleep(1)

    print("LLM worker stopped.", file=sys.stderr)


if __name__ == "__main__":
    run()

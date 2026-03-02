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
    
    print(f"Processing job for group {group_id} ({from_date} to {to_date})", file=sys.stderr, flush=True)

    while True:
        messages = db.fetch_unprocessed_messages(
            group_id=group_id,
            from_date=from_date,
            to_date=to_date,
            limit=BATCH_SIZE,
        )
        if not messages:
            print("No more unprocessed messages found.", file=sys.stderr, flush=True)
            break

        print(f"Processing batch of {len(messages)} messages...", file=sys.stderr, flush=True)
        
        try:
            trades = llm_client.extract_trades_from_messages(messages)
            print(f"Extracted {len(trades)} trades in this batch.", file=sys.stderr, flush=True)
            
            for t in trades:
                msg_ids = t.get("message_ids") or []
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
        except Exception as e:
            print(f"Error calling LLM: {e}", file=sys.stderr, flush=True)
            if "429" in str(e):
                print("Rate limit hit. Sleeping for 60s and retrying...", file=sys.stderr, flush=True)
                time.sleep(60)
                continue 
            
            # For other errors (like 404 model not found), we should also NOT mark as processed
            # effectively pausing the worker for this batch until fixed.
            print("Critical LLM error. Sleeping for 10s and retrying...", file=sys.stderr, flush=True)
            time.sleep(10)
            continue

        # CRITICAL FIX: Mark ALL fetched messages as processed, not just the ones with trades.
        # Otherwise we get stuck in an infinite loop reading the same non-trade messages.
        all_msg_ids = [m["id"] for m in messages]
        if all_msg_ids:
            db.mark_messages_processed(all_msg_ids)
            print(f"Marked {len(all_msg_ids)} messages as processed.", file=sys.stderr, flush=True)

        # Small sleep to be nice to the API rate limits if needed
        time.sleep(2)


def run():
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

    print("LLM worker started, waiting for jobs...", file=sys.stderr, flush=True)
    while not _shutdown:
        try:
            result = r.brpop(REDIS_LLM_QUEUE_KEY, timeout=POLL_TIMEOUT)
            if result is None:
                continue
            _key, value = result
            print(f"Received job: {value}", file=sys.stderr, flush=True)
            payload = json.loads(value)
            try:
                process_job(payload)
            except Exception as e:
                print(f"Job failed: {e}", file=sys.stderr, flush=True)
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

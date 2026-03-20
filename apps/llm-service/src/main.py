"""
LLM worker: consume jobs from Redis (arbitool:llm:jobs), fetch messages from PG,
call LLM to extract trades, write trades and mark messages as processed.
Supports parallel LLM calls for speed.
"""
import os
from pathlib import Path

# Load .env from llm-service directory (so it works from any cwd)
_env_dir = Path(__file__).resolve().parent.parent
_dotenv = _env_dir / ".env"
if _dotenv.exists():
    from dotenv import load_dotenv
    load_dotenv(_dotenv)
import json
import time
import signal
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import redis

from . import client as llm_client
from . import storage as db

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_LLM_QUEUE_KEY = "arbitool:llm:jobs"
BATCH_SIZE = int(os.environ.get("LLM_BATCH_SIZE", "50"))
BATCH_OVERLAP = int(os.environ.get("LLM_BATCH_OVERLAP", "15"))
POLL_TIMEOUT = int(os.environ.get("LLM_POLL_TIMEOUT", "30"))
PARALLEL_WORKERS = int(os.environ.get("LLM_PARALLEL_WORKERS", "3"))
# Un solo batch con todos los mensajes del job. True si LLM_SINGLE_BATCH=1 o si PROMPT_MODE=conversational (por defecto para chats chicos).
_sb = os.environ.get("LLM_SINGLE_BATCH", "").strip().lower()
_pm = os.environ.get("PROMPT_MODE", "").strip().lower()
SINGLE_BATCH = _sb in ("1", "true", "yes") or (_pm == "conversational" and _sb not in ("0", "false", "no"))
_shutdown = False


def handle_signal(_signum, _frame):
    global _shutdown
    _shutdown = True


def process_single_batch(batch_info: dict) -> dict:
    """Process a single batch with the LLM. Returns trades and batch metadata."""
    messages = batch_info["messages"]
    batch_num = batch_info["batch_num"]
    
    try:
        trades = llm_client.extract_trades_from_messages(messages)
        print(f"  [Batch {batch_num}] Extracted {len(trades)} trades", file=sys.stderr, flush=True)
        return {"success": True, "trades": trades, "batch_info": batch_info}
    except Exception as e:
        print(f"  [Batch {batch_num}] Error: {e}", file=sys.stderr, flush=True)
        return {"success": False, "error": str(e), "batch_info": batch_info}


def process_job(payload: dict) -> None:
    group_id = payload["group_id"]
    from_date = payload.get("from_date")
    to_date = payload.get("to_date")

    batch_size = 10000 if SINGLE_BATCH else BATCH_SIZE
    overlap = 0 if SINGLE_BATCH else BATCH_OVERLAP
    parallel = 1 if SINGLE_BATCH else PARALLEL_WORKERS

    print(f"Processing job for group {group_id} ({from_date} to {to_date})", file=sys.stderr, flush=True)
    print(f"Batch size: {batch_size}, overlap: {overlap}, parallel workers: {parallel}" + (" [SINGLE BATCH]" if SINGLE_BATCH else ""), file=sys.stderr, flush=True)

    seen_trade_keys: set[str] = set()
    seen_lock = threading.Lock()
    batch_num = 0

    while True:
        batches_to_process = []

        for _ in range(parallel):
            messages = db.fetch_messages_with_overlap(
                group_id=group_id,
                from_date=from_date,
                to_date=to_date,
                limit=batch_size,
                overlap=overlap,
            )
            if not messages:
                break

            unprocessed_ids = [m["id"] for m in messages if not m.get("_already_processed")]
            if not unprocessed_ids:
                break
            
            batch_num += 1
            batches_to_process.append({
                "messages": messages,
                "unprocessed_ids": unprocessed_ids,
                "batch_num": batch_num,
            })
            
            db.mark_messages_processed(unprocessed_ids)

        if not batches_to_process:
            print("No more unprocessed messages found.", file=sys.stderr, flush=True)
            break

        print(f"Processing {len(batches_to_process)} batches in parallel...", file=sys.stderr, flush=True)

        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {executor.submit(process_single_batch, batch): batch for batch in batches_to_process}
            
            for future in as_completed(futures):
                result = future.result()
                if not result["success"]:
                    error = result["error"]
                    if "429" in error:
                        print("Rate limit hit. Will slow down...", file=sys.stderr, flush=True)
                    continue
                
                trades = result["trades"]
                new_trades = 0
                
                for t in trades:
                    msg_ids = t.get("message_ids") or []
                    comprobante = t.get("comprobante_media_path") or ""
                    amount = t.get("amount") or t.get("fiat_amount")
                    
                    # Deduplicar por comprobante (cada imagen es única)
                    # Si no hay comprobante, usar comprobante|amount como fallback
                    trade_key = comprobante if comprobante else f"no_img|{amount}"
                    with seen_lock:
                        if trade_key in seen_trade_keys:
                            continue
                        seen_trade_keys.add(trade_key)
                    
                    currency = t.get("currency") or t.get("fiat_currency")
                    price_or_ref = t.get("price_or_ref") or t.get("cotizacion")
                    if price_or_ref is not None:
                        price_or_ref = str(price_or_ref)
                    
                    trade_date = t.get("trade_date")
                    comprobante_extra = t.get("comprobante_extra")
                    if comprobante_extra is not None and not isinstance(comprobante_extra, str):
                        comprobante_extra = json.dumps(comprobante_extra)

                    db.insert_trade(
                        group_id=group_id,
                        trade_type=t.get("type", "sell"),
                        amount=amount,
                        currency=currency,
                        price_or_ref=price_or_ref,
                        message_ids=msg_ids,
                        comprobante_media_path=comprobante,
                        raw_llm_response=t,
                        trade_date=trade_date,
                        bank=t.get("bank"),
                        sender_name=t.get("sender_name"),
                        cbu=t.get("cbu"),
                        transaction_id=t.get("transaction_id"),
                        id_colesa=t.get("id_colesa"),
                        comprobante_extra=comprobante_extra,
                    )
                    new_trades += 1
                
                batch_info = result["batch_info"]
                if new_trades < len(trades):
                    print(f"  [Batch {batch_info['batch_num']}] {new_trades} new trades ({len(trades) - new_trades} duplicates skipped)", file=sys.stderr, flush=True)

        time.sleep(1)


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

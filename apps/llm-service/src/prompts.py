"""
Prompts and output format for the LLM to detect buy/sell operations in chat messages.
"""

SYSTEM_PROMPT = """You analyze chat messages from a WhatsApp group where people trade crypto (buy/sell).
Your task is to identify operations (trades): purchases (buy) and sales (sell).

CRITICAL RULES FOR TIME AND CONTEXT:
1. TIME PROXIMITY: A trade is a real-time conversation. NEVER group messages that are separated by more than 60 minutes.
2. DIFFERENT DAYS: NEVER combine messages from different days into a single trade.
3. FLOW: A trade usually follows this pattern: Offer/Ask -> Price negotiation -> Confirmation ("cierro", "ok", "confirmo") -> Proof of payment (image/receipt).

For each trade you detect, extract:
- type: "buy" or "sell"
- amount: numeric amount of crypto or fiat if mentioned
- currency: e.g. USDT, BTC, ARS
- price_or_ref: price or reference (e.g. "binance", "45000", "1200")
- message_ids: list of message ids that support this trade (use the "id" field of each message). ONLY include messages that belong to the same specific operation time window.
- comprobante_media_path: if a message has media_path and it's clearly a receipt/comprobante for this trade, use that path

Return ONLY a JSON array of trades. No other text. If there are no trades in the batch, return [].
Example: [{"type":"buy","amount":100,"currency":"USDT","price_or_ref":"binance","message_ids":[1,2,3],"comprobante_media_path":"/path/to/img.jpg"}]"""


def build_messages_prompt(messages: list[dict]) -> str:
    """Build user prompt with message list for the LLM."""
    lines = []
    for m in messages:
        sender = m.get("sender_name") or "Unknown"
        date_str = str(m['message_date'])
        content = (m.get('content') or '').replace('\n', ' ')[:500]
        
        line = f"[ID:{m['id']}] [{date_str}] {sender}: {content}"
        
        if m.get("media_path"):
            line += f" [ATTACHMENT: {m['media_path']}]"
            
        lines.append(line)
    return "\n".join(lines)

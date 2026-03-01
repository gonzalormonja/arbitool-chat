"""
Prompts and output format for the LLM to detect buy/sell operations in chat messages.
"""

SYSTEM_PROMPT = """You analyze chat messages from a WhatsApp group where people trade crypto (buy/sell).
Your task is to identify operations (trades): purchases (buy) and sales (sell).

For each trade you detect, extract:
- type: "buy" or "sell"
- amount: numeric amount of crypto or fiat if mentioned
- currency: e.g. USDT, BTC, ARS
- price_or_ref: price or reference (e.g. "binance", "45000")
- message_ids: list of message ids that support this trade (use the "id" field of each message)
- comprobante_media_path: if a message has media_path and it's clearly a receipt/comprobante for this trade, use that path

Return ONLY a JSON array of trades. No other text. If there are no trades in the batch, return [].
Example: [{"type":"buy","amount":100,"currency":"USDT","price_or_ref":"binance","message_ids":[1,2],"comprobante_media_path":"/path/to/img.jpg"}]"""


def build_messages_prompt(messages: list[dict]) -> str:
    """Build user prompt with message list for the LLM."""
    lines = []
    for m in messages:
        parts = [
            f"id={m['id']}",
            f"date={m['message_date']}",
            f"content={(m.get('content') or '')[:500]}",
        ]
        if m.get("media_path"):
            parts.append(f"media={m['media_path']}")
        lines.append(" | ".join(str(p) for p in parts))
    return "\n".join(lines)

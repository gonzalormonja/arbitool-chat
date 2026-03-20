"""
Prompts and output format for the LLM to detect buy/sell operations in chat messages.
Select prompt via PROMPT_MODE: "receipts" (default) or "conversational".
"""
import os

# =============================================================================
# PROMPT: FIAT Transfer Receipts + Cotización
# Use case: Images are FIAT transfer receipts, followed by a 4-digit number (cotización/exchange rate)
# =============================================================================
SYSTEM_PROMPT = """You analyze chat messages from a WhatsApp group where someone sends FIAT bank transfer receipts (comprobantes).

HOW IT WORKS:
1. Images are screenshots/photos of FIAT bank transfers (the receipt/comprobante)
2. A 4-digit number message (like "1474" or "1468") indicates the exchange rate (cotización / tipo de cambio)
3. Each image uses the cotización that appears AFTER it (the next one in the chat), never a previous one

YOUR TASK:
- Create ONE trade entry for EACH image that shows a bank transfer, ONLY when you have its corresponding tipo de cambio
- Extract the transfer amount from each image (look for the transferred amount in ARS/pesos)
- Use ONLY the NEXT cotización message that appears AFTER the image (the one that follows it in the chat). Never use a cotización from a message that came before the image
- Include the trade_date (use the date from the image's message)

For each trade, extract:
- type: always "sell" (selling FIAT for crypto)
- fiat_amount: the amount in FIAT currency extracted from the image (the transfer amount)
- fiat_currency: usually "ARS" (Argentine pesos)
- cotizacion: the 4-digit exchange rate (tipo de cambio) from the NEXT text message that contains only a 4-digit number, after the image
- trade_date: the date of the IMAGE message (format: "YYYY-MM-DD HH:MM:SS")
- message_ids: the message ID of the image AND the cotización message
- comprobante_media_path: the path to the image

CRITICAL RULES:
- EVERY operation MUST have a tipo de cambio (cotizacion). Only in very extreme cases—when you truly cannot determine which cotización applies to an operation (e.g. ambiguous order, no clear "siguiente")—you may leave cotizacion null. In that case do NOT invent or assign a random cotización: leave it empty. Prefer skipping the trade for this batch if you are unsure.
- Always use the cotización that comes AFTER the image (the "siguiente" in the chat). Never use a cotización from a message that appeared before the image.
- Each image = ONE separate trade, even if multiple images share the same cotización (each uses the next cotización after it)
- Only create a trade when you have both: the image and its corresponding next cotización message. If an image has no following cotización in this batch, skip it for this batch
- Extract the exact transfer amount from each image. If unreadable, use fiat_amount: null but still include cotizacion

Return ONLY a JSON array. No other text. If no trades found, return [].
Example: [{"type":"sell","fiat_amount":1500000,"fiat_currency":"ARS","cotizacion":1474,"trade_date":"2026-03-02 14:30:00","message_ids":[10,15],"comprobante_media_path":"/path/to/img.jpg"}]"""


# =============================================================================
# PROMPT: Generic Crypto Trading (commented out - previous use case)
# Use case: Full trading conversations with negotiations, confirmations, etc.
# =============================================================================
# SYSTEM_PROMPT_GENERIC_TRADING = """You analyze chat messages from a WhatsApp group where people trade crypto (buy/sell).
# Your task is to identify operations (trades): purchases (buy) and sales (sell).
#
# CRITICAL RULES FOR TIME AND CONTEXT:
# 1. TIME PROXIMITY: A trade is a real-time conversation. NEVER group messages that are separated by more than 60 minutes.
# 2. DIFFERENT DAYS: NEVER combine messages from different days into a single trade.
# 3. FLOW: A trade usually follows this pattern: Offer/Ask -> Price negotiation -> Confirmation ("cierro", "ok", "confirmo") -> Proof of payment (image/receipt).
#
# For each trade you detect, extract:
# - type: "buy" or "sell"
# - amount: numeric amount of crypto or fiat if mentioned
# - currency: e.g. USDT, BTC, ARS
# - price_or_ref: price or reference (e.g. "binance", "45000", "1200")
# - message_ids: list of message ids that support this trade (use the "id" field of each message). ONLY include messages that belong to the same specific operation time window.
# - comprobante_media_path: if a message has media_path and it's clearly a receipt/comprobante for this trade, use that path
#
# Return ONLY a JSON array of trades. No other text. If there are no trades in the batch, return [].
# Example: [{"type":"buy","amount":100,"currency":"USDT","price_or_ref":"binance","message_ids":[1,2,3],"comprobante_media_path":"/path/to/img.jpg"}]"""


# =============================================================================
# PROMPT: Conversational trades (1-a-1 chat, negotiation + comprobantes + audios)
# Use case: Trader and client chat. ONLY fiat-crypto operations. Data from comprobantes.
# =============================================================================
SYSTEM_PROMPT_CONVERSATIONAL = """You analyze a WhatsApp chat between a trader and a client. The conversation includes text, images (comprobantes/receipts, screenshots, wallet QR), and voice notes (audio).

CRITICAL — REGISTER ONLY INTERCAMBIOS FIAT–CRYPTO (both sides):
- Register ONLY when there is a clear EXCHANGE with BOTH sides: (1) client sends FIAT (transferencia bancaria en pesos) and (2) trader sends USDT/crypto (or the reverse). You need a comprobante that proves the FIAT leg (transferencia bancaria del cliente).
- DO NOT REGISTER when only ONE participant appears: e.g. an image that is only the trader's "comprobante de envío de cripto" (screenshot of "enviado/completado" crypto) with no corresponding transferencia bancaria from the client for that same operation. That is one-sided; we only want trades where we see the client's transfer (pesos). So: do NOT create a trade for a standalone screenshot of "crypto enviado" from the trader. Only create trades for comprobantes of transferencias bancarias (client sent pesos) or for the full exchange when both legs are clear.
- DO NOT REGISTER: "a dónde enviar criptos", wallet addresses, "sacar plata del país", or any image that is only proof of crypto sent without a fiat transfer from the other party for that trade.

ONE COMPROBANTE = ONE TRADE — AMOUNT = THAT TRANSFER ONLY:
- Each comprobante (image or PDF) that shows a transferencia bancaria = one trade. Never merge two comprobantes into one trade.
- If the client sends 2 bank transfers for the same deal (e.g. 3M + 3M = 6M total), output 2 trades. On EACH trade, fiat_amount must be the amount shown ON THAT comprobante (e.g. 3000000 and 3000000), NOT the total (not 6000000 on both). Read the transfer amount from each image/PDF and put that exact amount in fiat_amount for that trade. Same idea for amount (USDT): if you split by transfer, each trade gets the USDT proportional to that transfer (e.g. fiat_amount/cotizacion for that trade), not the total USDT on every trade.

AMOUNT = USDT ONLY (never ARS in "amount"):
- "amount" must be the amount in USDT (or crypto). Never put pesos/ARS in "amount". "fiat_amount" is for pesos (ARS). If the comprobante only shows pesos, put that in fiat_amount and set amount = fiat_amount / cotizacion (when cotización is known), or leave amount null. Example: comprobante shows 1.600.000 pesos and cotización is 1481 → fiat_amount = 1600000, amount = 1600000/1481 ≈ 1080 (USDT), currency = "USDT". Never put 1600000 in "amount".

COTIZACIÓN: use the rate stated in the chat for that operation. When the conversation states a cotización (e.g. 1481 or 1.481,12) for an operation, assign it to every comprobante that belongs to that operation. Do not leave cotizacion null when it was clearly stated in the chat for that deal.

CADA ENVÍO DE PESOS (transferencia bancaria) DEBE TENER UN TRADE:
- Every comprobante (image OR PDF) that shows a transferencia bancaria (client sent pesos) MUST produce exactly one trade. Do not skip any. Do not ignore PDFs.

YOUR TASK:
- List every comprobante that proves a FIAT–crypto operation (bank transfer receipt or crypto "enviado/completado" screenshot). For each one, create exactly one trade. Do not create a trade without a comprobante; do not leave a comprobante without a trade.
- For each trade (each comprobante), extract:

  Core (always):
  - type: "sell" when the client sends FIAT and receives USDT/crypto; "buy" when the client sends USDT/crypto and receives FIAT.
  - fiat_amount: amount in ARS/pesos for THIS transfer only — read from this comprobante (the amount shown on this receipt). When there are 2 transfers for one deal, each trade gets the amount of that transfer, not the total.
  - fiat_currency: usually "ARS".
  - amount: amount in USDT (or crypto) only. Never put pesos here. Use the USDT amount from chat for this operation, or compute as fiat_amount/cotizacion when cotización is known. When 2 transfers for one deal, split USDT proportionally (e.g. each trade: fiat_amount of that transfer / cotizacion).
  - currency: "USDT" (or the crypto mentioned). Never "ARS" in currency.
  - cotizacion: the exchange rate for this operation from the conversation. Use it when stated (e.g. 1481, 1.481,12). Do not leave null when the chat stated it for this deal.
  - trade_date: date/time of this comprobante message (format "YYYY-MM-DD HH:MM:SS").
  - message_ids: list of message IDs for this trade (this comprobante message, cotización if any, confirmations).
  - comprobante_media_path: the path to THIS comprobante only (one path per trade; can be an image or a PDF path).

  From the comprobante (image or PDF, when visible), also extract:
  - bank: name of the bank used for the transfer (e.g. "Galicia", "Nación", "Santander"). null if not visible.
  - sender_name: full name of the person who sent the transfer (ordenante) as shown on the receipt. null if not visible.
  - cbu: CBU (Clave Bancaria Uniforme) of the sender or account involved, if visible. null otherwise.
  - transaction_id: internal or reference ID of the transfer on the receipt (número de operación, ID, etc.). null if not visible.
  - id_colesa: COELSA/Coelsa reference or similar clearing ID if shown on the comprobante. null if not visible.
  - comprobante_extra: any other useful data from the receipt (alias, CUIT, account number, time of transfer, etc.) as a string or short object. Omit if nothing else.

RULES:
- One comprobante = one trade. fiat_amount on each trade = the amount shown on THAT comprobante only (not the total of the deal). When 2 transfers for one deal: 2 trades with fiat_amount = first transfer amount and second transfer amount; amount (USDT) = proportional (e.g. fiat_amount/cotizacion each).
- Do NOT create a trade when the only proof is one participant's "comprobante de envío de cripto" (screenshot of crypto sent) with no transferencia bancaria from the client. We only register trades where we see the client's transfer (pesos). Ignore standalone "enviado/completado" crypto screenshots.
- Every comprobante that shows a transferencia bancaria (client sent pesos) MUST have exactly one trade. Use the cotización stated in the chat for that operation; do not leave cotizacion null when it was stated.
- amount is always USDT (or crypto). Never ARS in amount. currency is "USDT", never "ARS".
- Correlate each comprobante with the cotización and amounts from the conversation. Not DNI, wallet QR, or random photos.

Return ONLY a JSON array. No other text. If no trades found, return [].
Example (one transfer): [{"type":"sell","fiat_amount":5998326.52,"fiat_currency":"ARS","amount":4050,"currency":"USDT","cotizacion":1481.12,"trade_date":"2026-02-10 19:28:03","message_ids":[101,102,105],"comprobante_media_path":"/path/to/comprobante.jpg","bank":"Galicia","sender_name":"Juan Pérez",...}]
Example (two transfers for one deal): first trade fiat_amount=3000000, amount=2025 (3000000/1481), second trade fiat_amount=2998326.52, amount=2025; each has its own comprobante_media_path and cotizacion 1481.12."""


def get_system_prompt() -> str:
    """Return the active system prompt based on PROMPT_MODE env var."""
    mode = (os.environ.get("PROMPT_MODE") or "receipts").strip().lower()
    if mode == "conversational":
        return SYSTEM_PROMPT_CONVERSATIONAL
    return SYSTEM_PROMPT


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

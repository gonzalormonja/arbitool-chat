"""
LLM client (OpenAI-compatible) for structured trade extraction.
"""
import os
import json
import re
from openai import OpenAI

from . import prompts

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required")
        _client = OpenAI(api_key=api_key)
    return _client


def extract_trades_from_messages(messages: list[dict]) -> list[dict]:
    """
    Call the LLM to extract buy/sell trades from a batch of messages.
    Returns a list of dicts with type, amount, currency, price_or_ref, message_ids, comprobante_media_path.
    """
    if not messages:
        return []

    user_content = prompts.build_messages_prompt(messages)
    client = get_client()
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompts.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
    )
    text = response.choices[0].message.content or ""

    # Parse JSON array from response (allow for markdown code blocks)
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return []

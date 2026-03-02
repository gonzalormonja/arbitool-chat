"""
LLM client (OpenAI-compatible) for structured trade extraction.
"""
import os
import json
import re
import sys
from openai import OpenAI
import google.generativeai as genai

from . import prompts

_client: OpenAI | None = None
_genai_configured = False


def get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL")
        
        # If base_url is provided (e.g. for Ollama), api_key might be optional/dummy
        if not api_key and not base_url:
            raise RuntimeError("OPENAI_API_KEY (or OPENAI_BASE_URL) is required")
            
        _client = OpenAI(
            api_key=api_key or "dummy",
            base_url=base_url
        )
    return _client


def extract_trades_from_messages(messages: list[dict]) -> list[dict]:
    """
    Call the LLM to extract buy/sell trades from a batch of messages.
    Returns a list of dicts with type, amount, currency, price_or_ref, message_ids, comprobante_media_path.
    """
    if not messages:
        return []

    user_content = prompts.build_messages_prompt(messages)
    
    # Check if we should use Gemini
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        return _extract_with_gemini(gemini_key, user_content)

    # Fallback to OpenAI/Groq/Ollama
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
    print(f"LLM Response: {text}", file=sys.stderr) # Uncomment for debugging

    return _parse_json_response(text)


def _extract_with_gemini(api_key: str, user_content: str) -> list[dict]:
    global _genai_configured
    if not _genai_configured:
        genai.configure(api_key=api_key)
        _genai_configured = True
    
    model_name = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
    model = genai.GenerativeModel(model_name)
    
    # Gemini doesn't use system prompts the same way, we prepend it
    full_prompt = f"{prompts.SYSTEM_PROMPT}\n\nHere are the messages:\n{user_content}"
    
    try:
        response = model.generate_content(full_prompt)
        text = response.text
        print(f"Gemini Response: {text}", file=sys.stderr)
        return _parse_json_response(text)
    except Exception as e:
        print(f"Gemini Error: {e}", file=sys.stderr)
        raise e


def _parse_json_response(text: str) -> list[dict]:
    # Parse JSON array from response (allow for markdown code blocks)
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return []

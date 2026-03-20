"""
LLM client (OpenAI-compatible) for structured trade extraction.
Supports vision (multimodal) when images are present in the batch.
"""
import os
import json
import re
import sys
from pathlib import Path
from openai import OpenAI
import google.generativeai as genai
from PIL import Image

from . import prompts

_client: OpenAI | None = None
_genai_configured = False

# Image extensions we support for vision
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}

# Audio extensions we support (voice notes, etc.) - Gemini can transcribe/understand
AUDIO_EXTENSIONS = {'.ogg', '.opus', '.mp3', '.m4a', '.webm', '.wav', '.mp4', '.mpeg', '.mpga'}
AUDIO_MIME = {
    '.ogg': 'audio/ogg',
    '.opus': 'audio/ogg',  # WhatsApp voice notes often .opus
    '.mp3': 'audio/mpeg',
    '.m4a': 'audio/mp4',
    '.webm': 'audio/webm',
    '.wav': 'audio/wav',
    '.mp4': 'audio/mp4',
    '.mpeg': 'audio/mpeg',
    '.mpga': 'audio/mpeg',
}
# Max size for inline audio (bytes) - skip larger files to avoid API limits
AUDIO_MAX_INLINE_BYTES = 20 * 1024 * 1024  # 20 MB

# PDF comprobantes - Gemini can read PDFs
PDF_EXTENSIONS = {".pdf"}
PDF_MAX_INLINE_BYTES = 20 * 1024 * 1024  # 20 MB
PDF_MIME = "application/pdf"


def get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL")
        
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
    
    If the batch contains images, uses vision (multimodal) to analyze them.
    """
    if not messages:
        return []

    # Check if we should use Gemini
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        return _extract_with_gemini(gemini_key, messages)

    # Fallback to OpenAI/Groq/Ollama (text only for now)
    user_content = prompts.build_messages_prompt(messages)
    client = get_client()
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompts.get_system_prompt()},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
    )
    text = response.choices[0].message.content or ""
    print(f"LLM Response: {text}", file=sys.stderr)

    return _parse_json_response(text)


def _get_image_paths_from_messages(messages: list[dict]) -> list[tuple[int, str]]:
    """
    Extract (message_id, image_path) tuples for messages that have valid image attachments.
    Only returns paths that exist and are image files.
    """
    image_paths = []
    for m in messages:
        media_path = m.get("media_path")
        if media_path:
            path = Path(media_path)
            if path.exists() and path.suffix.lower() in IMAGE_EXTENSIONS:
                image_paths.append((m['id'], str(path)))
    return image_paths


def _get_audio_paths_from_messages(messages: list[dict]) -> list[tuple[int, str]]:
    """
    Extract (message_id, audio_path) for messages that have audio attachments (voice notes, etc.).
    Only returns paths that exist, are audio files, and are under AUDIO_MAX_INLINE_BYTES.
    """
    audio_paths = []
    for m in messages:
        media_path = m.get("media_path")
        if media_path:
            path = Path(media_path)
            if not path.exists() or path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            try:
                if path.stat().st_size > AUDIO_MAX_INLINE_BYTES:
                    print(f"Skipping large audio {path} ({path.stat().st_size} bytes)", file=sys.stderr)
                    continue
            except OSError:
                continue
            audio_paths.append((m['id'], str(path)))
    return audio_paths


def _get_pdf_paths_from_messages(messages: list[dict]) -> list[tuple[int, str]]:
    """
    Extract (message_id, pdf_path) for messages that have PDF attachments (comprobantes, etc.).
    Gemini can read PDFs; we send them as inline_data.
    """
    pdf_paths = []
    for m in messages:
        media_path = m.get("media_path")
        if media_path:
            path = Path(media_path)
            if not path.exists() or path.suffix.lower() not in PDF_EXTENSIONS:
                continue
            try:
                if path.stat().st_size > PDF_MAX_INLINE_BYTES:
                    print(f"Skipping large PDF {path} ({path.stat().st_size} bytes)", file=sys.stderr)
                    continue
            except OSError:
                continue
            pdf_paths.append((m["id"], str(path)))
    return pdf_paths


def _extract_with_gemini(api_key: str, messages: list[dict]) -> list[dict]:
    """
    Extract trades using Gemini. Uses vision if there are images in the batch.
    """
    global _genai_configured
    if not _genai_configured:
        genai.configure(api_key=api_key)
        _genai_configured = True
    
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    model = genai.GenerativeModel(model_name)
    
    # Build text prompt
    user_content = prompts.build_messages_prompt(messages)
    
    # Check for images, audio and/or PDFs
    image_paths = _get_image_paths_from_messages(messages)
    audio_paths = _get_audio_paths_from_messages(messages)
    pdf_paths = _get_pdf_paths_from_messages(messages)

    if image_paths or audio_paths or pdf_paths:
        # Use multimodal (vision + optional audio + optional PDFs)
        return _extract_with_gemini_multimodal(model, user_content, image_paths, audio_paths, pdf_paths)
    else:
        # Text-only mode
        return _extract_with_gemini_text(model, user_content)


def _extract_with_gemini_text(model, user_content: str) -> list[dict]:
    """Text-only extraction with Gemini."""
    full_prompt = f"{prompts.get_system_prompt()}\n\nHere are the messages:\n{user_content}"
    
    try:
        response = model.generate_content(full_prompt)
        text = response.text
        print(f"Gemini Response (text-only): {text}", file=sys.stderr)
        return _parse_json_response(text)
    except Exception as e:
        print(f"Gemini Error: {e}", file=sys.stderr)
        raise e


def _extract_with_gemini_multimodal(
    model,
    user_content: str,
    image_paths: list[tuple[int, str]],
    audio_paths: list[tuple[int, str]],
    pdf_paths: list[tuple[int, str]] | None = None,
) -> list[dict]:
    """
    Multimodal extraction with Gemini - sends text + images + optional audio + optional PDFs.
    """
    pdf_paths = pdf_paths or []
    print(
        f"Using multimodal: {len(image_paths)} images, {len(audio_paths)} audio, {len(pdf_paths)} PDFs",
        file=sys.stderr,
    )

    content_parts = []

    # Build intro: what we're sending
    media_note = []
    if image_paths:
        media_note.append("images (receipts/comprobantes)")
    if pdf_paths:
        media_note.append("PDFs (comprobantes)")
    if audio_paths:
        media_note.append("audio (voice notes)")
    media_note_str = " and ".join(media_note)

    vision_prompt = f"""{prompts.get_system_prompt()}

IMPORTANT: You are receiving {media_note_str} along with the chat messages.
- Images and PDFs are receipts/comprobantes: extract amount, currency, reference, date, bank, sender from them. Each PDF page or image that shows a transfer is a comprobante and must have one trade.
- Audio are voice notes: transcribe and use any mentioned amounts, cotizaciones, or trade details to complete or confirm trades.

Each media is labeled with the message ID (e.g. "Image for message ID: 123" or "PDF for message ID: 456"). Use that to correlate with the chat and set comprobante_media_path (path to that image or PDF). Do not skip comprobantes that are PDFs: they count the same as images.

Here are the messages:
{user_content}

Now I will show you the media from the chat:"""

    content_parts.append(vision_prompt)

    # Add images
    for msg_id, img_path in image_paths:
        try:
            img = Image.open(img_path)
            max_size = 1024
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            content_parts.append(f"\n--- Image for message ID: {msg_id} (path: {img_path}) ---")
            content_parts.append(img)
        except Exception as e:
            print(f"Warning: Could not load image {img_path}: {e}", file=sys.stderr)
            continue

    # Add audio as inline_data (mime_type + data)
    for msg_id, audio_path in audio_paths:
        try:
            path = Path(audio_path)
            mime = AUDIO_MIME.get(path.suffix.lower(), "audio/mpeg")
            data = path.read_bytes()
            content_parts.append(f"\n--- Audio (voice note) for message ID: {msg_id} ---")
            content_parts.append({"inline_data": {"mime_type": mime, "data": data}})
        except Exception as e:
            print(f"Warning: Could not load audio {audio_path}: {e}", file=sys.stderr)
            continue

    # Add PDFs as inline_data (Gemini can read PDFs)
    for msg_id, pdf_path in pdf_paths:
        try:
            path = Path(pdf_path)
            data = path.read_bytes()
            content_parts.append(f"\n--- PDF (comprobante) for message ID: {msg_id} (path: {pdf_path}) ---")
            content_parts.append({"inline_data": {"mime_type": PDF_MIME, "data": data}})
        except Exception as e:
            print(f"Warning: Could not load PDF {pdf_path}: {e}", file=sys.stderr)
            continue

    content_parts.append(
        "\n\nAnalyze all messages, images, PDFs and audio above and return the JSON array of detected trades. Every comprobante (image or PDF) must have exactly one trade."
    )

    try:
        response = model.generate_content(content_parts)
        text = response.text
        print(f"Gemini Response (multimodal): {text}", file=sys.stderr)
        return _parse_json_response(text)
    except Exception as e:
        print(f"Gemini Multimodal Error: {e}", file=sys.stderr)
        raise e


def _parse_json_response(text: str) -> list[dict]:
    """Parse JSON array from response (allow for markdown code blocks).
    If the response is truncated (e.g. output token limit), recover all complete objects."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Response may be truncated (e.g. 350+ trades hit output token limit)
        if text.startswith("[") and '"type":' in text:
            # Find last complete object: boundary is },"type": or },\n"type":
            last_complete = max(
                text.rfind('},"type":'),
                text.rfind('},\n"type":'),
                text.rfind('},\r\n"type":'),
            )
            if last_complete >= 0:
                truncated = text[: last_complete + 1] + "]"
                try:
                    recovered = json.loads(truncated)
                    print(
                        f"Recovered {len(recovered)} trades from truncated JSON (output was cut off).",
                        file=sys.stderr,
                    )
                    return recovered
                except json.JSONDecodeError:
                    pass
        print(f"Warning: Could not parse JSON response: {text[:200]}...", file=sys.stderr)
        return []

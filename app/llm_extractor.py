import base64
import json
import logging
from anthropic import Anthropic, APIError
from app.config import settings
from app.master_schema import MASTER_SCHEMA

logger = logging.getLogger(__name__)

# only construct the client if a key is actually present — avoids init-time surprises too
client = Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

SYSTEM_PROMPT = """You are a document data extraction assistant. You extract structured
data from student/academic documents (ID cards, marksheets, certificates, forms).

Rules:
- Return ONLY valid JSON, no markdown fences, no preamble.
- JSON must have exactly two keys: "extracted_fields" and "confidence".
- Only include fields you can actually find explicit evidence for in the document.
- Never guess or hallucinate — if a field isn't visibly present, omit it entirely.
- confidence is a 0.0-1.0 score per field you included.
- Normalize dates to YYYY-MM-DD.
"""

class ExtractionError(Exception):
    pass

class LLMNotConfiguredError(ExtractionError):
    """Raised when the LLM fallback is requested but no API key is configured."""
    pass


async def extract_with_llm(text: str | None, image_bytes: bytes | None, media_type: str | None) -> dict:
    if not settings.llm_available:
        logger.warning("LLM extraction skipped — no API key configured or fallback disabled")
        raise LLMNotConfiguredError("LLM extraction unavailable: no ANTHROPIC_API_KEY configured")

    field_list = "\n".join(f"- {k}: {v}" for k, v in MASTER_SCHEMA.items())
    user_prompt = f"Extract any of these fields that are present in the document:\n{field_list}"

    try:
        if text:
            message = client.messages.create(
                model=settings.llm_model,
                max_tokens=1500,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"{user_prompt}\n\nDocument text:\n{text[:15000]}"}],
            )
        elif image_bytes:
            b64_image = base64.b64encode(image_bytes).decode("utf-8")
            message = client.messages.create(
                model=settings.llm_model,
                max_tokens=1500,
                system=SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_image}},
                        {"type": "text", "text": user_prompt},
                    ],
                }],
            )
        else:
            raise ExtractionError("No text or image available for extraction")

        return _parse_response(message)

    except APIError as e:
        logger.error(f"LLM API error: {e}")
        raise ExtractionError(f"LLM API error: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"LLM returned invalid JSON: {e}")
        raise ExtractionError("LLM returned invalid JSON")


def _parse_response(message) -> dict:
    text = message.content[0].text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    data = json.loads(text.strip())
    extracted = {k: v for k, v in data.get("extracted_fields", {}).items() if k in MASTER_SCHEMA}
    confidence = {k: v for k, v in data.get("confidence", {}).items() if k in extracted}
    return {"extracted_fields": extracted, "confidence": confidence}
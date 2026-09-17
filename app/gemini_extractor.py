import json
import logging
import asyncio
from google import genai
from google.genai import types
from app.config import settings
from app.master_schema import MASTER_SCHEMA
from app.extraction_utils import filter_placeholders

logger = logging.getLogger(__name__)

client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None

SYSTEM_PROMPT = """You are a document data extraction assistant. You extract structured
data from student/academic/government-issued documents (ID cards, marksheets, certificates,
caste/domicile certificates, forms).

Rules:
- Only include fields you can actually find explicit evidence for in the document.
- Never guess or hallucinate — if a field isn't visibly present, leave it out.
- confidence is a 0.0-1.0 score for how certain you are about that field's value.
- Normalize dates to YYYY-MM-DD.
- Village/district/state are often embedded in a sentence rather than labeled separately —
  e.g. "of Village X in District Y, State of Z" or "resides in the Y District of Z" — extract
  village, district, and state as separate fields whenever you see this pattern, even without
  an explicit "Address:" label. Only use the 'address' field itself for a full address given
  as one continuous labeled block.
- For subject-wise marks: add one entry per subject to the 'subjects' array. Do not put
  subject marks into 'fields'.
- Never guess or hallucinate — if a field isn't visibly present, DO NOT add it to the
  output at all. Do not write "not mentioned", "N/A", "unknown", or any placeholder —
  simply omit that field_name entirely from the 'fields' array.
- Some documents include a reference/document number combining a printed prefix with a
  handwritten insertion (e.g. "No. MSC/SR/OBC/[handwritten]/200"). Capture the ENTIRE
  reference string as printed, including every prefix/suffix segment — not just the
  handwritten portion.
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "fields": {...},  # unchanged
        "subject_wise_marks": {  # renamed from "subjects"
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "marks_obtained": {"type": "string"},
                    "max_marks": {"type": "string"},
                },
                "required": ["subject", "marks_obtained"],
            },
        },
    },
    "required": ["fields", "subject_wise_marks"],
}

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

class ExtractionError(Exception):
    pass

class LLMNotConfiguredError(ExtractionError):
    pass


async def extract_with_gemini(text: str | None, image_bytes: bytes | None, media_type: str | None) -> dict:
    if not settings.llm_available or client is None:
        raise LLMNotConfiguredError("Gemini extraction unavailable: no GEMINI_API_KEY configured")

    field_list = "\n".join(f"- {k}: {v}" for k, v in MASTER_SCHEMA.items() if k != "subjects_marks")
    user_prompt = (
        f"Extract any of these fields present in the document into 'fields':\n{field_list}\n\n"
        f"Separately, extract subject-wise marks into 'subjects' — one entry per subject."
    )

    if image_bytes:
        contents = [user_prompt, types.Part.from_bytes(data=image_bytes, mime_type=media_type)]
    elif text:
        contents = f"{user_prompt}\n\nDocument text:\n{text[:15000]}"
    else:
        raise ExtractionError("No text or image available for extraction")

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        max_output_tokens=4096,
        response_mime_type="application/json",
        response_schema=RESPONSE_SCHEMA,
        thinking_config=types.ThinkingConfig(thinking_level="low"),
    )

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(model=settings.gemini_model, contents=contents, config=config)
            logger.info(f"Gemini raw response: {response.text!r}")

            if not response.text:
                raise ExtractionError("Gemini returned an empty response")

            return _parse_response(response.text)

        except json.JSONDecodeError as e:
            raise ExtractionError(f"Gemini returned invalid JSON: {e}")
        except Exception as e:
            last_error = e
            is_retryable = "503" in str(e) or "UNAVAILABLE" in str(e) or "429" in str(e)
            if is_retryable and attempt < MAX_RETRIES:
                delay = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                logger.warning(f"Gemini call failed (attempt {attempt}/{MAX_RETRIES}), retrying in {delay}s: {e}")
                await asyncio.sleep(delay)
                continue
            raise ExtractionError(f"Gemini API error: {e}")

    raise ExtractionError(f"Gemini API error after {MAX_RETRIES} attempts: {last_error}")


def _parse_response(text: str) -> dict:
    data = json.loads(text.strip())
    extracted = {}
    confidence = {}

    for entry in data.get("fields", []):
        name = entry.get("field_name")
        if name in MASTER_SCHEMA:
            extracted[name] = entry.get("value")
            confidence[name] = entry.get("confidence", 0.7)

    subjects = data.get("subject_wise_marks", [])
    if subjects:
        extracted["subjects_marks"] = subjects
        confidence["subjects_marks"] = 1.0

    extracted, confidence = filter_placeholders(extracted, confidence)
    return {"extracted_fields": extracted, "confidence": confidence}
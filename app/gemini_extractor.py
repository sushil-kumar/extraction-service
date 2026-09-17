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
- ALWAYS include a 'document_type' entry in 'fields' as your very first entry, classifying
  the document as one of: marksheet, caste_certificate, leaving_certificate, id_card,
  domicile_certificate, income_certificate, other. This is required even if you're unsure —
  pick the closest match.
- Only include fields you can actually find explicit evidence for in the document.
- Never guess or hallucinate — if a field isn't visibly present, DO NOT add it to the output
  at all. Do not write "not mentioned", "N/A", "unknown", or any placeholder — simply omit
  that field_name entirely from the 'fields' array.
- confidence is a 0.0-1.0 score for how certain you are about that field's value.
- Normalize dates to YYYY-MM-DD.
- Subject-wise marks are IMPORTANT and MUST be extracted whenever a marks table is present:
  add one entry per subject to the 'subject_wise_marks' array, with subject name and marks
  obtained. Do not put subject marks into 'fields'.
- If the document has no subject-wise marks table at all (e.g. leaving certificates, caste
  certificates), do NOT add any entries to 'subject_wise_marks' — leave the array completely
  empty rather than adding a placeholder entry.
- Some documents include a reference/document number combining a printed prefix with a
  handwritten insertion. Capture the ENTIRE reference string as printed.
- Geographic details appear in different patterns depending on document type. Two common
  patterns on Maharashtra documents:
  1. "Village X in District Y, State of Z" (caste/domicile certificates) — extract village,
     district, and state directly.
  2. "Place, Tal. Taluka (District)" e.g. "Chinchgharpada, Tal. Wada (Thane)" — here "Tal."
     introduces the TALUKA (not district), and the bracketed name afterward is the DISTRICT.
     Do not put the Taluka value into 'district' — use the 'taluka' field for it. Only put
     a value into 'state' if a state name is explicitly present; do not infer or guess it.
- When a date is given BOTH in words and in bracketed numeric form (e.g. "Twenty December
  Nineteen Eighty Two (20/12/1982)"), read the word form carefully and use it to verify the
  numeric form — they must match. If they conflict, prefer whichever one you can read with
  higher certainty, and lower your confidence score for that field if there's any ambiguity
  between the two given forms.
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
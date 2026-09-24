import json
import logging
import asyncio
from google import genai
from google.genai import types
from app.config import settings
from app.extraction_utils import filter_placeholders

logger = logging.getLogger(__name__)

client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None

SYSTEM_PROMPT = """You are a document data extraction assistant. You extract structured
data from student/academic/government-issued documents (ID cards, marksheets, certificates,
caste/domicile certificates, forms, land records, society registration documents). Documents
may be in English, Marathi, or a mix of both — read and extract regardless of language.

Rules:
- ALWAYS include a 'document_type' entry in 'fields' as your very first entry, classifying
  the document using the categories given in the field list below. This is required even if
  you're unsure — pick the closest match.
- Only include fields you can actually find explicit evidence for in the document.
- Never guess or hallucinate — if a field isn't visibly present, DO NOT add it to the output
  at all, in ANY language. Do not write "not mentioned" or any equivalent phrase in English,
  Hindi, Marathi, or any other language — simply omit that field_name entirely from the
  'fields' array.
- confidence is a 0.0-1.0 score for how certain you are about that field's value.
- Normalize dates to YYYY-MM-DD.
- Subject-wise marks are IMPORTANT and MUST be extracted whenever a marks table is present:
  add one entry per subject to the 'subject_wise_marks' array, with subject name and marks
  obtained. Do not put subject marks into 'fields'.
- Subject marks are copied exactly as printed, digit by digit — never truncated or adjusted
  to "look normal." EXAMPLE: a composite subject like "Fresh Water Fish Culture" can be worth
  200 total marks, so a mark of "186" (three digits, greater than 100) is correct and must
  NOT be shortened to "86" just because most other subjects on the same marksheet cap at 100.
- On a marksheet's 'Total Marks' row, do not confuse the maximum possible total with the
  actual total obtained — they appear as two separate numbers. EXAMPLE: "Total Marks: 600 |
  398 | THREE HUNDRED AND NINETYEIGHT" — the correct total_marks value is 398 (confirmed by
  the word form), NOT 600 (which is the maximum).
- If the document has no subject-wise marks table at all (e.g. leaving certificates, caste
  certificates), do NOT add any entries to 'subject_wise_marks' — leave the array completely
  empty rather than adding a placeholder entry.
- Reference/document numbers are ALWAYS a single field, even when part of the number is
  handwritten and part is printed. Never split one reference number across two separate
  field entries. EXAMPLE: if a document shows a printed line reading "No. MSC/SR/OBC/" then
  a handwritten insertion "R-4921" then printed "/200", the correct output is ONE field
  entry with value "MSC/SR/OBC/R-4921/200" — not two entries, one for the prefix and one
  for the handwritten part.
- Geographic details appear in different patterns depending on document type. Two common
  patterns on Maharashtra documents:
  1. "Village X in District Y, State of Z" — extract village, district, and state directly.
  2. "Place, Tal. Taluka (District)" e.g. "Chinchgharpada, Tal. Wada (Thane)" — here "Tal."
     introduces the TALUKA (not district), and the bracketed name afterward is the DISTRICT.
     Do not put the Taluka value into 'district' — use the 'taluka' field for it. Only put
     a value into 'state' if a state name is explicitly present; do not infer or guess it.
- When a date is given BOTH in words and in bracketed numeric form, read each digit of the
  bracketed form carefully, one at a time, and cross-check the decade/unit digits specifically
  against the spelled-out words. EXAMPLE: "Twenty December Nineteen Eighty Two (20/12/1982)"
  — the words "Eighty Two" confirm the year ends in 82, so the correct date_of_birth is
  "1982-12-20". Do not transpose or misread digits in the bracketed form; if the two forms
  genuinely conflict after careful digit-by-digit reading, lower your confidence score for
  that field rather than guessing.
- On the FRONT of an Aadhaar card specifically, the 12-digit Aadhaar number usually appears
  with NO label at all — just three groups of 4 digits at the bottom of the card (format:
  'XXXX XXXX XXXX'). This unlabeled number IS the Aadhaar number. If document_type is
  aadhaar_card and you see an unlabeled 12-digit number in this exact grouped format, route
  it to 'aadhaar_number' — do NOT put it in 'document_number', 'roll_number', or
  'certificate_number', even though it has no visible label.
- Standard Aadhaar cards show ONLY: name, date of birth, gender, address, and Aadhaar number
  (plus the issuing authority "Unique Identification Authority of India"). They do NOT
  normally include a father's or mother's name field. Do not populate father_name or
  mother_name for an aadhaar_card unless there is an explicit, clearly labeled "Father's
  Name" or "S/O" field printed on the card — never infer a name from a signature, stamp, or
  unrelated text elsewhere on the document.
- On a PAN card, the PAN number often appears on its OWN line, directly below a section
  heading ("Permanent Account Number Card" / "स्थायी लेखा संख्या कार्ड"), rather than inline
  with a "PAN No:" label. The value itself is always exactly 10 characters: 5 uppercase
  letters + 4 digits + 1 uppercase letter (e.g. 'BPJPS8242D'). If document_type is pan_card
  and you see a standalone 10-character code matching this exact pattern anywhere on the
  card, extract it as 'pan_number' — do not skip it just because there's no inline label
  directly touching it.
- Never combine digits or fragments from two different, separately-located numbers on the
  document into a single value. If a mutation number or date field isn't clearly labeled
  with its own explicit value nearby, omit that field entirely rather than constructing one
  from nearby unrelated reference codes or footnote numbers.
- Devanagari numerals १ (1) and ९ (9) can look visually similar in blurry or low-quality
  scans. Read khata numbers, survey numbers, and other Devanagari-digit fields carefully,
  digit by digit, and lower your confidence score if any digit is genuinely ambiguous.
"""

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

class ExtractionError(Exception):
    pass

class LLMNotConfiguredError(ExtractionError):
    pass


def _build_response_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "fields": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field_name": {"type": "string"},
                        "value": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["field_name", "value", "confidence"],
                },
            },
            "subject_wise_marks": {
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
            "land_owners": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "khata_number": {"type": "string"},
                        "owner_name": {"type": "string"},
                        "area": {"type": "string"},
                        "assessment": {"type": "string"},
                    },
                    "required": ["khata_number", "owner_name"],
                },
            },
        },
        "required": ["fields"],  # only fields is mandatory — the two array types are optional per-module
    }

def _build_generation_config() -> types.GenerateContentConfig:
    config_kwargs = {
        "system_instruction": SYSTEM_PROMPT,
        "max_output_tokens": 4096,
        "response_mime_type": "application/json",
        "response_schema": _build_response_schema(),
    }

    # Not all installed versions of the google-genai SDK expose ThinkingConfig
    # under this name/location — degrade gracefully rather than crash if it's
    # missing, since thinking behavior is an optimization, not a requirement.
    if hasattr(types, "ThinkingConfig"):
        try:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level="low")
        except Exception as e:
            logger.warning(f"Could not set thinking_config (SDK version mismatch?): {e}")

    return types.GenerateContentConfig(**config_kwargs)

async def extract_with_gemini(
    text: str | None, image_bytes: bytes | None, media_type: str | None,
    schema: dict, array_field: str | None = None,
) -> dict:
    if not settings.llm_available or client is None:
        raise LLMNotConfiguredError("Gemini extraction unavailable: no GEMINI_API_KEY configured")

    field_list = "\n".join(f"- {k}: {v}" for k, v in schema.items())

    if array_field == "subject_wise_marks":
        array_instruction = "Separately, extract subject-wise marks into 'subject_wise_marks' if a marks table is present."
    elif array_field == "land_owners":
        array_instruction = "Separately, extract each landholder into 'land_owners' if the document lists multiple owners."
    else:
        array_instruction = ""

    user_prompt = f"Extract any of these fields present in the document into 'fields':\n{field_list}\n\n{array_instruction}"

    if image_bytes:
        contents = [user_prompt, types.Part.from_bytes(data=image_bytes, mime_type=media_type)]
    elif text:
        contents = f"{user_prompt}\n\nDocument text:\n{text[:15000]}"
    else:
        raise ExtractionError("No text or image available for extraction")

    config = _build_generation_config()

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(model=settings.gemini_model, contents=contents, config=config)
            logger.info(f"Gemini raw response: {response.text!r}")

            if not response.text:
                raise ExtractionError("Gemini returned an empty response")

            return _parse_response(response.text, schema)

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


def _parse_response(text: str, schema: dict) -> dict:
    data = json.loads(text.strip())
    extracted = {}
    confidence = {}

    for entry in data.get("fields", []):
        name = entry.get("field_name")
        if name in schema:
            extracted[name] = entry.get("value")
            confidence[name] = entry.get("confidence", 0.7)

    subjects = data.get("subject_wise_marks", [])
    if subjects:
        extracted["subjects_marks"] = subjects
        confidence["subjects_marks"] = 1.0

    owners = data.get("land_owners", [])
    if owners:
        extracted["land_owners"] = owners
        confidence["land_owners"] = 1.0

    extracted, confidence = filter_placeholders(extracted, confidence, schema=schema)
    return {"extracted_fields": extracted, "confidence": confidence}
import json
import re
import ast
import logging
from ollama import Client
from pydantic import BaseModel
from app.config import settings
from app.master_schema import MASTER_SCHEMA
from app.extraction_utils import filter_placeholders

logger = logging.getLogger(__name__)

client = Client(host=settings.ollama_host)

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

class ExtractionError(Exception):
    pass

class FieldEntry(BaseModel):
    field_name: str
    value: str
    confidence: float

class SubjectMark(BaseModel):
    subject: str
    marks_obtained: str
    max_marks: str = ""

class ExtractionSchema(BaseModel):
    fields: list[FieldEntry]
    subject_wise_marks: list[SubjectMark] = []


def _parse_subjects_fallback(raw_value: str) -> list[dict] | None:
    """The model is inconsistent about how it formats subject data when it
    ignores the proper schema array — plain JSON, Python-dict-literal syntax
    (single-quoted), comma-separated 'SUBJECT: MARKS', or newline-separated
    'subject: X, marks_obtained: Y'. Try each in order, since we've now
    observed all four formats in practice."""
    raw_value = raw_value.strip()

    # Attempt 1: plain JSON (possibly prefixed with a label)
    try:
        cleaned = raw_value if raw_value.startswith("[") else (
            raw_value.split(":", 1)[-1].strip() if ":" in raw_value else raw_value
        )
        parsed = json.loads(cleaned)
        if isinstance(parsed, list) and len(parsed) > 0:
            return parsed
    except (json.JSONDecodeError, AttributeError):
        pass

    # Attempt 2: Python dict-literal syntax (single-quoted) — [{'subject': 'X', ...}, ...]
    try:
        cleaned = raw_value if raw_value.startswith("[") else (
            raw_value.split(":", 1)[-1].strip() if ":" in raw_value else raw_value
        )
        parsed = ast.literal_eval(cleaned)
        if isinstance(parsed, list) and len(parsed) > 0 and all(isinstance(x, dict) for x in parsed):
            return parsed
    except (ValueError, SyntaxError):
        pass

    # Attempt 3: generic regex — finds "subject ... marks_obtained" key:value pairs
    pattern = re.compile(
        r'["\']?subject["\']?\s*:\s*["\']?([^,"\'\n]+?)["\']?\s*,?\s*'
        r'["\']?marks_obtained["\']?\s*:\s*["\']?([^,"\'\n]+?)["\']?\s*(?:,|\n|\}|$)',
        re.IGNORECASE,
    )
    matches = pattern.findall(raw_value)
    entries = []
    for subject, marks in matches:
        subject = re.sub(r"^[A-Z0-9]{1,3}\s+", "", subject.strip())
        marks = marks.strip()
        if subject and marks:
            entries.append({"subject": subject, "marks_obtained": marks, "max_marks": ""})
    if entries:
        return entries

    # Attempt 4: simple "SUBJECT: MARKS, SUBJECT: MARKS" comma list, no explicit keys
    entries = []
    for chunk in raw_value.split(","):
        chunk = chunk.strip()
        if ":" not in chunk:
            continue
        subject_part, marks_part = chunk.rsplit(":", 1)
        subject = re.sub(r"^[A-Z0-9]{1,3}\s+", "", subject_part.strip())
        marks = marks_part.strip()
        if subject and marks and subject.lower() not in ("subject", "marks_obtained"):
            entries.append({"subject": subject, "marks_obtained": marks, "max_marks": ""})
    return entries if entries else None


async def extract_with_ollama(image_bytes: bytes, media_type: str) -> dict:
    field_list = "\n".join(f"- {k}: {v}" for k, v in MASTER_SCHEMA.items() if k != "subjects_marks")
    user_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Extract any of these fields present in the document. For each one found, "
        f"add an entry to 'fields' with field_name (must match exactly), value, and confidence.\n\n{field_list}\n\n"
        f"IMPORTANT — subject-wise marks: do NOT create a field_name called 'subjects', "
        f"'subject_wise_marks', or 'subjects_marks' inside 'fields'. Instead, use the separate "
        f"top-level 'subject_wise_marks' array. Add one entry per subject there, with 'subject', "
        f"'marks_obtained', and 'max_marks'. CRITICAL: marks_obtained must be copied EXACTLY as "
        f"the single number printed in that subject's marks column — do not calculate, split, sum, "
        f"or infer it from max_marks or any other value. If a subject shows one combined number "
        f"(e.g. for a vocational/composite subject), report that exact number as marks_obtained, "
        f"even if it looks unusual relative to max_marks."
    )

    keep_alive_value = settings.ollama_keep_alive
    if keep_alive_value.strip() == "-1":
        keep_alive_value = -1

    response = client.chat(
        model=settings.ollama_model,
        messages=[{"role": "user", "content": user_prompt, "images": [image_bytes]}],
        format=ExtractionSchema.model_json_schema(),
        options={"temperature": 0, "num_ctx": 12288, "num_predict": 2048},
        keep_alive=keep_alive_value,
    )

    if response is None:
        logger.error("Ollama client.chat() returned None")
        raise ExtractionError("Ollama returned no response object")

    if isinstance(response, dict):
        message = response.get("message")
        content = message.get("content") if message else None
    else:
        message = getattr(response, "message", None)
        content = getattr(message, "content", None) if message else None

    if content is None:
        logger.error(f"Ollama response had no message content. Full response: {response}")
        raise ExtractionError("Ollama response contained no content")

    logger.info(f"Ollama raw content: {content!r}")

    try:
        parsed = ExtractionSchema.model_validate_json(content)
    except Exception as e:
        logger.error(f"Failed to parse Ollama content as ExtractionSchema: {e}. Raw content: {content!r}")
        raise ExtractionError(f"Ollama returned unparseable structured output: {e}")

    extracted = {}
    confidence = {}
    for entry in parsed.fields:
        if entry is not None and entry.field_name in MASTER_SCHEMA:
            extracted[entry.field_name] = entry.value
            confidence[entry.field_name] = entry.confidence

    # Recover subject data even if the model stuffed it into 'fields' instead
    # of using the proper 'subject_wise_marks' array.
    SUBJECT_FIELD_ALIASES = {"subjects", "subject_wise_marks", "subjects_marks"}
    recovered_subjects = None

    for alias in SUBJECT_FIELD_ALIASES:
        if alias in extracted:
            raw_value = extracted.pop(alias)
            confidence.pop(alias, None)
            recovered_subjects = _parse_subjects_fallback(raw_value)
            if recovered_subjects is None:
                logger.warning(f"Could not parse subject data recovered from field '{alias}': {raw_value!r}")
            break

    if recovered_subjects:
        extracted["subjects_marks"] = recovered_subjects
        confidence["subjects_marks"] = 0.85
    elif parsed.subject_wise_marks:
        extracted["subjects_marks"] = [
            {"subject": s.subject, "marks_obtained": s.marks_obtained, "max_marks": s.max_marks}
            for s in parsed.subject_wise_marks
        ]
        confidence["subjects_marks"] = 1.0

    extracted, confidence = filter_placeholders(extracted, confidence)
    return {"extracted_fields": extracted, "confidence": confidence}
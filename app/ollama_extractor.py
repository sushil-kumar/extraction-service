import json
import re
import ast
import logging
from ollama import Client
from pydantic import BaseModel
from app.config import settings
from app.extraction_utils import filter_placeholders

logger = logging.getLogger(__name__)

client = Client(host=settings.ollama_host)

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

class LandOwner(BaseModel):
    khata_number: str
    owner_name: str
    area: str = ""
    assessment: str = ""

class ExtractionSchema(BaseModel):
    fields: list[FieldEntry]
    subject_wise_marks: list[SubjectMark] = []
    land_owners: list[LandOwner] = []


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

def _parse_keyvalue_list_fallback(raw_value: str, keys: list[str]) -> list[dict] | None:
    """Generalized version of the subject-marks recovery parser — handles the
    same JSON / Python-literal / regex-pair / comma-list formats, for any
    ordered pair of keys (e.g. khata_number+owner_name instead of subject+marks_obtained)."""
    raw_value = raw_value.strip()
    key_a, key_b = keys[0], keys[1]

    try:
        cleaned = raw_value if raw_value.startswith("[") else (
            raw_value.split(":", 1)[-1].strip() if ":" in raw_value else raw_value
        )
        parsed = json.loads(cleaned)
        if isinstance(parsed, list) and len(parsed) > 0:
            return parsed
    except (json.JSONDecodeError, AttributeError):
        pass

    try:
        cleaned = raw_value if raw_value.startswith("[") else (
            raw_value.split(":", 1)[-1].strip() if ":" in raw_value else raw_value
        )
        parsed = ast.literal_eval(cleaned)
        if isinstance(parsed, list) and len(parsed) > 0 and all(isinstance(x, dict) for x in parsed):
            return parsed
    except (ValueError, SyntaxError):
        pass

    pattern = re.compile(
        rf'["\']?{key_a}["\']?\s*:\s*["\']?([^,"\'\n]+?)["\']?\s*,?\s*'
        rf'["\']?{key_b}["\']?\s*:\s*["\']?([^,"\'\n]+?)["\']?\s*(?:,|\n|\}}|$)',
        re.IGNORECASE,
    )
    matches = pattern.findall(raw_value)
    entries = [{key_a: a.strip(), key_b: b.strip()} for a, b in matches if a.strip() and b.strip()]
    return entries if entries else None

class ExtractionSchemaBase(BaseModel):
    fields: list[FieldEntry]
    subject_wise_marks: list[SubjectMark] = []
    land_owners: list[LandOwner] = []
    # both remain valid pydantic fields on the class — but we only PROMPT for
    # and PARSE the one relevant to this module, so the other stays empty and
    # doesn't dilute the model's attention via the prompt text itself.

async def extract_with_ollama(image_bytes: bytes, media_type: str, schema: dict, array_field: str) -> dict:
    field_list = "\n".join(f"- {k}: {v}" for k, v in schema.items())

    if array_field == "subject_wise_marks":
        array_instruction = (
            f"IMPORTANT — subject-wise marks: do NOT create a field_name called 'subjects', "
            f"'subject_wise_marks', or 'subjects_marks' inside 'fields'. Instead, use the "
            f"separate top-level 'subject_wise_marks' array. Add one entry per subject there, "
            f"with 'subject', 'marks_obtained', and 'max_marks'. CRITICAL: marks_obtained must "
            f"be copied EXACTLY as the single number printed in that subject's marks column."
        )
    elif array_field == "land_owners":
        array_instruction = (
            f"IMPORTANT — for land records with multiple owners/khatedars, use the top-level "
            f"'land_owners' array, NOT a field_name inside 'fields'. One entry per owner, with "
            f"khata_number, owner_name, area, and assessment."
        )
    else:
        array_instruction = ""

    user_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Extract any of these fields present in the document. For each one found, "
        f"add an entry to 'fields' with field_name (must match exactly), value, and confidence.\n\n{field_list}\n\n"
        f"{array_instruction}"
    )

    keep_alive_value = settings.ollama_keep_alive
    if keep_alive_value.strip() == "-1":
        keep_alive_value = -1

    response = client.chat(
        model=settings.ollama_model,
        messages=[{"role": "user", "content": user_prompt, "images": [image_bytes]}],
        format=ExtractionSchemaBase.model_json_schema(),
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
        parsed = ExtractionSchemaBase.model_validate_json(content)
    except Exception as e:
        logger.error(f"Failed to parse Ollama content: {e}. Raw content: {content!r}")
        raise ExtractionError(f"Ollama returned unparseable structured output: {e}")

    extracted = {}
    confidence = {}
    for entry in parsed.fields:
        if entry is not None and entry.field_name in schema:
            extracted[entry.field_name] = entry.value
            confidence[entry.field_name] = entry.confidence

    # only attempt recovery/parsing for the array relevant to THIS module
    if array_field == "subject_wise_marks":
        SUBJECT_FIELD_ALIASES = {"subjects", "subject_wise_marks", "subjects_marks"}
        recovered = None
        for alias in SUBJECT_FIELD_ALIASES:
            if alias in extracted:
                raw_value = extracted.pop(alias)
                confidence.pop(alias, None)
                recovered = _parse_subjects_fallback(raw_value)
                break

        if recovered:
            extracted["subjects_marks"] = recovered
            confidence["subjects_marks"] = 0.85
        elif parsed.subject_wise_marks:
            extracted["subjects_marks"] = [
                {"subject": s.subject, "marks_obtained": s.marks_obtained, "max_marks": s.max_marks}
                for s in parsed.subject_wise_marks
            ]
            confidence["subjects_marks"] = 1.0

    elif array_field == "land_owners":
        LAND_OWNER_ALIASES = {"land_owners", "landowners", "owners"}
        recovered = None
        for alias in LAND_OWNER_ALIASES:
            if alias in extracted:
                raw_value = extracted.pop(alias)
                confidence.pop(alias, None)
                recovered = _parse_keyvalue_list_fallback(raw_value, ["khata_number", "owner_name"])
                break

        if recovered:
            extracted["land_owners"] = recovered
            confidence["land_owners"] = 0.85
        elif parsed.land_owners:
            extracted["land_owners"] = [
                {"khata_number": o.khata_number, "owner_name": o.owner_name, "area": o.area, "assessment": o.assessment}
                for o in parsed.land_owners
            ]
            confidence["land_owners"] = 1.0

    extracted, confidence = filter_placeholders(extracted, confidence)
    return {"extracted_fields": extracted, "confidence": confidence}
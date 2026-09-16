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
- Some documents include a reference/document number that combines a printed prefix with a
  handwritten insertion (e.g. "No. MSC/SR/OBC/[handwritten]/200"). Capture the ENTIRE reference
  string as printed, including all prefix segments — not just the handwritten portion.
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
    subjects: list[SubjectMark] = []


async def extract_with_ollama(image_bytes: bytes, media_type: str) -> dict:
    field_list = "\n".join(f"- {k}: {v}" for k, v in MASTER_SCHEMA.items() if k != "subjects_marks")
    user_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Extract any of these fields present in the document. For each one found, "
        f"add an entry to 'fields' with field_name (must match exactly), value, and confidence.\n\n{field_list}\n\n"
        f"Separately, extract subject-wise marks into the 'subjects' array."
    )

    response = client.chat(
        model=settings.ollama_model,
        messages=[{"role": "user", "content": user_prompt, "images": [image_bytes]}],
        format=ExtractionSchema.model_json_schema(),
        options={"temperature": 0, "num_ctx": 8192},
    )

    # defensive checks — log exactly what came back before touching it
    if response is None:
        logger.error("Ollama client.chat() returned None")
        raise ExtractionError("Ollama returned no response object")

    # logger.info(f"Ollama response type: {type(response)}, keys/attrs: {dir(response) if not isinstance(response, dict) else response.keys()}")

    # handle both dict-style and object-style responses (ollama SDK versions differ)
    if isinstance(response, dict):
        message = response.get("message")
        content = message.get("content") if message else None
    else:
        message = getattr(response, "message", None)
        content = getattr(message, "content", None) if message else None

    if content is None:
        logger.error(f"Ollama response had no message content. Full response: {response}")
        raise ExtractionError("Ollama response contained no content")

    # logger.info(f"Ollama raw content: {content!r}")

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

    if parsed.subjects:
        extracted["subjects_marks"] = [
            {"subject": s.subject, "marks_obtained": s.marks_obtained, "max_marks": s.max_marks}
            for s in parsed.subjects
        ]
        confidence["subjects_marks"] = 1.0

    extracted, confidence = filter_placeholders(extracted, confidence)
    return {"extracted_fields": extracted, "confidence": confidence}
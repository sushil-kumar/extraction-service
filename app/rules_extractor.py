import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Only fields where the OCR text has "label followed directly by value" —
# regex is reliable here. Values are kept on one OCR line so a following
# field label is not accidentally included in the capture.
FIELD_PATTERNS = {
    "candidate_name": [
        (r"(?:candidate'?s?|student'?s?|applicant'?s?)\s*(?:full\s*)?name\s*[:\-]?\s*([A-Z][A-Za-z.'\- ]{2,60})", 0.85),
        (r"name\s*of\s*(?:the\s*)?(?:candidate|student|applicant)\s*[:\-]?\s*([A-Z][A-Za-z.'\- ]{2,60})", 0.85),
    ],
    "father_name": [
        (r"(?:father'?s?|guardian'?s?)\s*name\s*[:\-]?\s*([A-Z][A-Za-z.'\- ]{2,60})", 0.85),
        (r"(?:s/?o|son\s+of|f/?o)\s*[:\-]?\s*([A-Z][A-Za-z.'\- ]{2,60})", 0.75),
    ],
    "mother_name": [
        (r"(?:mother'?s?)\s*name\s*[:\-]?\s*([A-Z][A-Za-z.'\- ]{2,60})", 0.85),
    ],
    "roll_number": [
        (r"(?:roll|enrol(?:l)?ment|registration|student\s*id)\s*(?:no|number|id)?\s*[:#.\-]?\s*([A-Z0-9][A-Z0-9\-/]{3,19})", 0.85),
    ],
    "date_of_birth": [
        (r"(?:date\s*of\s*birth|dob|d\.\s*o\.\s*b)\s*[:\-]?\s*(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})", 0.85),
        (r"(?:date\s*of\s*birth|dob|d\.\s*o\.\s*b)\s*[:\-]?\s*(\d{1,2}\s+\w+\s+\d{4})", 0.8),
    ],
    "gender": [
        (r"(?:gender|sex)\s*[:\-]?\s*(female|male|other|transgender|f|m)", 0.9),
    ],
    "address": [
        (r"(?:permanent\s+address|residential\s+address|address)\s*[:\-]?\s*([^\r\n]{10,150})", 0.7),
    ],
    "seat_number": [
        (r"(?:seat|exam\s*seat)\s*(?:no|number)?\s*[:#.\-]?\s*([A-Z0-9][A-Z0-9\-/]{2,19})", 0.85),
    ],
    "centre_number": [
        (r"(?:centre|center|exam\s*centre|exam\s*center)\s*(?:no|number|code)?\s*[:#.\-]?\s*([A-Z0-9][A-Z0-9\-/]{1,19})", 0.85),
    ],
    "school_number": [
        (r"(?:school|college|institution)\s*(?:no|number|code)\s*[:#.\-]?\s*([A-Z0-9][A-Z0-9\-/]{1,19})", 0.85),
    ],
    "board_name": [
        (r"(?:board|examining\s+body|university)\s*(?:name)?\s*[:\-]?\s*([^\r\n]{3,100})", 0.75),
    ],
    "stream": [
        (r"(?:stream|branch|faculty)\s*[:\-]?\s*(science|commerce|arts|humanities|engineering|medical|[A-Za-z][A-Za-z &/\-]{2,40})", 0.75),
    ],
    "exam_month_year": [
        (r"(?:exam(?:ination)?\s*(?:month\s*(?:and|&)\s*year|session|year)|month\s*of\s*exam)\s*[:\-]?\s*([^\r\n]{4,30})", 0.75),
    ],
    "percentage": [
        (r"(?:percentage|percent|%age)\s*[:\-/a-z\s]*?(\d{1,3}(?:\.\d{1,2})?)\s*%?", 0.85),
    ],
    "total_marks": [
        (r"(?:total\s*marks|marks\s*obtained|total)\s*[:\-]?\s*(\d{1,4}(?:\s*/\s*\d{1,4})?)", 0.8),
    ],
    "result": [
        (r"\b(?:result|status)\b\s*[:\-]?\s*(pass(?:ed)?|fail(?:ed)?|distinction|first\s*class|second\s*class|[A-Z]+)", 0.9),
    ],
    "certificate_number": [
        (r"(?:certificate|statement)\s*(?:no|number)\s*[:#.\-]?\s*([A-Z0-9][A-Z0-9\-/]{2,29})", 0.85),
    ],
    "document_number": [
        (r"(?:document|application|admission|registration)\s*(?:no|number|id)\s*[:#.\-]?\s*([A-Z0-9][A-Z0-9\-/]{2,29})", 0.8),
    ],
    "issue_date": [
        (r"(?:date\s*of\s*issue|issued\s*on|issue\s*date)\s*[:\-]?\s*(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})", 0.8),
        (r"(?:date\s*of\s*issue|issued\s*on|issue\s*date)\s*[:\-]?\s*(\d{1,2}\s+\w+\s+\d{4})", 0.75),
    ],
    "issuing_authority": [
        (r"(?:issuing\s+authority|issued\s+by)\s*[:\-]?\s*([^\r\n]{3,100})", 0.75),
    ],
}


def normalize_date(raw: str) -> str | None:
    formats = ["%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y", "%d %B %Y", "%d %b %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def extract_with_rules(text: str) -> dict:
    """Free, regex-based extraction — only for label-inline fields where
    regex is reliable. Returns empty for anything it's not confident about."""
    extracted_fields = {}
    confidence = {}

    if not text:
        return {"extracted_fields": {}, "confidence": {}}

    for field, patterns in FIELD_PATTERNS.items():
        for pattern, base_confidence in patterns:
            try:
                match = re.search(pattern, text, re.IGNORECASE)
            except re.error as e:
                logger.error(f"Invalid regex for field '{field}': {e}")
                continue

            if match:
                value = match.group(1).strip()

                if field == "date_of_birth":
                    normalized = normalize_date(value)
                    if normalized:
                        extracted_fields[field] = normalized
                        confidence[field] = base_confidence
                        break
                else:
                    extracted_fields[field] = value
                    confidence[field] = base_confidence
                    break

    return {"extracted_fields": extracted_fields, "confidence": confidence}
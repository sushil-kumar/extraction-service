import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Only fields where the OCR text has "label followed directly by value" —
# regex is reliable here. Values are kept on one OCR line so a following
# field label is not accidentally included in the capture.
FIELD_PATTERNS = {
    "candidate_name": [
        (r"(?:candidate['\u2019]?s?|student['\u2019]?s?|applicant['\u2019]?s?)\s*(?:full\s*)?name\s*(?:\([^\r\n)]*\))?\s*[:\-]?\s*([A-Z][A-Za-z.'\- ]{2,60})", 0.9),
        (r"name\s*of\s*(?:the\s*)?(?:candidate|student|applicant)\s*[:\-]?\s*([A-Z][A-Za-z.'\- ]{2,60})", 0.85),
        (r"(?:this\s+is\s+to\s+certify\s+that|certify\s+that)\s+([A-Za-z][A-Za-z.'\-]*(?:[ \t]+[A-Za-z][A-Za-z.'\-]*){1,5})[ \t]*(?:\r?\n|$)", 0.95),
        (r"(?:mr|ms|mrs|miss)\s*/?\s*(?:mr|ms|mrs|miss)?\.?[ \t]+([A-Za-z][A-Za-z.\-]*(?:[ \t]+[A-Za-z][A-Za-z.\-]*){1,5})[ \t]*(?:\r?\n|$)", 0.8),
    ],
    "father_name": [
        (r"(?:father'?s?|guardian'?s?)\s*name\s*[:\-]?\s*([A-Z][A-Za-z.'\- ]{2,60})", 0.85),
        (r"(?:s/?o|son\s+of)\s*[:\-]\s*([A-Z][A-Za-z.'\- ]{2,60})", 0.75),
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
    "board_name": [
        (r"(?:board|examining\s+body|university)\s*(?:name)?\s*[:\-]\s*([^\r\n]{5,100})", 0.75),
    ],
    "stream": [
        (r"(?:stream|branch|faculty)\s*[:\-]?\s*(science|commerce|arts|humanities|engineering|medical)", 0.9),
    ],
    "exam_month_year": [
        (r"(?:exam(?:ination)?\s*(?:month\s*(?:and|&)\s*year|session|year)|month\s*of\s*exam)\s*[:\-]?\s*([^\r\n]{4,30})", 0.75),
    ],
    "percentage": [
        (r"(?:percentage|percent|%age)[^\r\n]{0,30}\b(100(?:\.\d{1,2})?|[0-9]?\d(?:\.\d{1,2})?)\s*%?", 0.85),
    ],
    "result": [
        (r"\b(?:result|status)\b\s*[:\-]?\s*(pass(?:ed)?|fail(?:ed)?|distinction|first\s*class\s*(?:with\s*distinction)?|second\s*class|third\s*class|absent)\b", 0.9),
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
    "village": [
        (r"(?:village|gram)\s+(?:of\s+)?([A-Z][A-Za-z\s]{2,40})(?:\s+in\s+district|\s*,)", 0.75),
    ],
    "district": [
        (r"district\s+([A-Z][A-Za-z\s]{2,40})(?:,|\s+state)", 0.75),
    ],
    "state": [
        (r"state\s+of\s+([A-Z][A-Za-z]+)(?:\s+belongs|\.|,|\s*\n)", 0.75),
    ],
    "caste": [
        (r"belongs\s+to\s+the\s+([A-Za-z\-\s]{2,50})\s+caste", 0.8),
    ],
    "caste_category": [
        (r"(other\s+backward\s+class|obc|scheduled\s+caste|sc|scheduled\s+tribe|st|open|general)", 0.7),
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


def normalize_candidate_name(raw: str) -> str:
    """Remove academic degree suffixes that OCR may append to a name."""
    value = re.sub(r"\s+[,;\-]?\s*(?:B\.?A\.?|B\.?SC\.?|B\.?COM\.?|M\.?A\.?|M\.?SC\.?|M\.?COM\.?|DIPLOMA)\s*$", "", raw, flags=re.IGNORECASE)
    return value.strip(" ,;-")


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
                try:
                    value = match.group(1).strip()
                except IndexError:
                    logger.error(f"Pattern for field '{field}' has no capture group: {pattern}")
                    continue  # skip this pattern, try the next one for this field

                if field == "candidate_name":
                    value = normalize_candidate_name(value)
                    if value:
                        extracted_fields[field] = value
                        confidence[field] = base_confidence
                        break
                elif field == "date_of_birth":
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
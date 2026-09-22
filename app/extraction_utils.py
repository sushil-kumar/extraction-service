import re

PLACEHOLDER_VALUES = {
    "not mentioned", "not available", "not found", "not visible",
    "not present", "not applicable", "n/a", "na", "none", "nil",
    "unknown", "-", "--", "not specified", "not given", "not stated",
    # Hindi/Marathi equivalents — the model sometimes responds in the
    # document's own language for a "not found" case instead of English
    "नहीं दिखाई", "उपलब्ध नाही", "नमूद नाही", "उपलब्ध नहीं",
    "दिसत नाही", "अनुपलब्ध", "माहीत नाही", "अज्ञात", "उल्लेख नाही",
}


def is_placeholder_value(value) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    cleaned = value.strip().lower()
    return cleaned == "" or cleaned in PLACEHOLDER_VALUES


def filter_placeholders(extracted_fields: dict, confidence: dict) -> tuple[dict, dict]:
    clean_fields = {}
    clean_confidence = {}
    for field, value in extracted_fields.items():
        if not is_placeholder_value(value):
            clean_fields[field] = value
            clean_confidence[field] = confidence.get(field, 0.0)
    return clean_fields, clean_confidence


def get_fields_requiring_review(extracted_fields: dict, review_fields: set) -> list[str]:
    """Fields present in the result that this module's schema flags for manual
    review, regardless of the LLM's own reported confidence."""
    return [field for field in extracted_fields if field in review_fields]


def clean_subjects_marks(extracted_fields: dict) -> dict:
    subjects = extracted_fields.get("subjects_marks")
    if not subjects or not isinstance(subjects, list):
        return extracted_fields

    real_entries = [
        entry for entry in subjects
        if isinstance(entry, dict)
        and not is_placeholder_value(entry.get("subject"))
        and not is_placeholder_value(entry.get("marks_obtained"))
    ]

    if real_entries:
        extracted_fields["subjects_marks"] = real_entries
    else:
        extracted_fields.pop("subjects_marks", None)

    return extracted_fields


def validate_subject_marks_sum(extracted_fields: dict) -> str | None:
    subjects = extracted_fields.get("subjects_marks")
    total = extracted_fields.get("total_marks")
    if not subjects or not total:
        return None

    subject_sum = 0.0
    numeric_subject_count = 0

    for s in subjects:
        raw = str(s.get("marks_obtained", "")).strip()
        match = re.match(r"^(\d+(?:\.\d+)?)", raw)  # leading number, ignoring any trailing "(WORD FORM)" or grade text
        if match:
            subject_sum += float(match.group(1))
            numeric_subject_count += 1

    if numeric_subject_count == 0:
        return None  # no numeric subjects at all (e.g. all grade-only) — nothing to validate

    try:
        reported_total = float(total)
    except (ValueError, TypeError):
        return None

    if abs(subject_sum - reported_total) > 1:
        return (
            f"Subject marks sum to {subject_sum:.0f} (from {numeric_subject_count} numeric subjects) "
            f"but total_marks reports {reported_total:.0f} — possible missing subject or extraction error"
        )

    return None

def is_valid_pan_format(value: str) -> bool:
    """PAN structure: 5 letters (first 3 alpha series, 4th = holder type, 5th = surname
    initial), 4 digits, 1 check letter. This only validates the FORMAT, not that the PAN
    is real/active — that would require a government API lookup, out of scope here."""
    return bool(re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", value.strip()))


def is_valid_aadhaar_format(value: str) -> bool:
    """Aadhaar structural check: exactly 12 digits, doesn't start with 0 or 1
    (UIDAI never issues Aadhaar numbers starting with those digits)."""
    digits = re.sub(r"\s", "", value)
    return bool(re.match(r"^[2-9]\d{11}$", digits))

# app/extraction_utils.py — new function
def validate_id_number_formats(extracted_fields: dict) -> list[str]:
    """Returns field names whose value fails a structural format check —
    a strong signal of misread, independent of the LLM's own confidence."""
    warnings = []
    if "pan_number" in extracted_fields and not is_valid_pan_format(extracted_fields["pan_number"]):
        warnings.append("pan_number")
    if "aadhaar_number" in extracted_fields and not is_valid_aadhaar_format(extracted_fields["aadhaar_number"]):
        warnings.append("aadhaar_number")
    return warnings

def deduplicate_identity_number(extracted_fields: dict) -> dict:
    """If aadhaar_number is present and some other generic 'number' field
    holds the exact same value, the model has misrouted it — clear the
    duplicate rather than trust the prompt to avoid this every time."""
    aadhaar = extracted_fields.get("aadhaar_number")

    if aadhaar:
        for generic_field in ("document_number", "roll_number", "certificate_number", "certificate_serial_number"):
            if extracted_fields.get(generic_field) == aadhaar:
                extracted_fields.pop(generic_field)
        return extracted_fields

    # aadhaar_number itself is MISSING, but one of the generic fields holds
    # something that looks like an Aadhaar number (12 digits, 4-4-4 grouped)
    # — this is the exact misrouting you just hit. Recover it.
    aadhaar_shape = re.compile(r"^\d{4}\s\d{4}\s\d{4}$")
    for generic_field in ("document_number", "roll_number", "certificate_number"):
        value = extracted_fields.get(generic_field, "")
        if isinstance(value, str) and aadhaar_shape.match(value.strip()):
            extracted_fields["aadhaar_number"] = value
            extracted_fields.pop(generic_field)
            break

    return extracted_fields

# Fields that are valid to expect on each document_type. Anything the model
# populates outside this set for a recognized type gets stripped — this is a
# deliberate code-level guard against hallucination, since prompt instructions
# alone haven't reliably prevented the model from inventing fields (e.g.
# fabricating a father_name on an Aadhaar card that has no such field at all).
DOCUMENT_TYPE_FIELD_WHITELIST = {
    "aadhaar_card": {
        "document_type", "candidate_name", "date_of_birth", "gender",
        "address", "aadhaar_number", "issuing_authority",
    },
    "pan_card": {
        "document_type", "candidate_name", "father_name",
        "date_of_birth", "pan_number",
    },
    # marksheet, caste_certificate, leaving_certificate, land_record, etc.
    # intentionally left unrestricted for now — their field sets are more
    # variable and already validated well through the regression suite.
    # Add entries here only for document types where hallucination has been
    # observed, so this stays a targeted fix, not a maintenance burden across
    # every type.
}


def enforce_document_type_whitelist(extracted_fields: dict, confidence: dict) -> tuple[dict, dict]:
    doc_type = extracted_fields.get("document_type")
    whitelist = DOCUMENT_TYPE_FIELD_WHITELIST.get(doc_type)
    if not whitelist:
        return extracted_fields, confidence  # no whitelist defined for this type — leave as-is

    clean_fields = {k: v for k, v in extracted_fields.items() if k in whitelist}
    clean_confidence = {k: v for k, v in confidence.items() if k in whitelist}
    return clean_fields, clean_confidence

# app/extraction_utils.py

def normalize_document_type(extracted_fields: dict) -> dict:
    """The model sometimes classifies a document too generically (e.g. 'id_card'
    instead of 'aadhaar_card'), which breaks downstream logic that keys off the
    exact document_type value (like the field whitelist). Where we have a
    reliable structural signal — a correctly-shaped Aadhaar or PAN number — use
    that to correct the classification rather than trusting the model's label."""
    import re

    aadhaar = extracted_fields.get("aadhaar_number", "")
    if isinstance(aadhaar, str) and re.match(r"^\d{4}\s?\d{4}\s?\d{4}$", aadhaar.strip()):
        extracted_fields["document_type"] = "aadhaar_card"
        return extracted_fields

    pan = extracted_fields.get("pan_number", "")
    if isinstance(pan, str) and re.match(r"^[A-Z]{5}\d{4}[A-Z]$", pan.strip()):
        extracted_fields["document_type"] = "pan_card"
        return extracted_fields

    return extracted_fields

def assess_text_quality(text: str) -> float:
    """Rough heuristic score (0.0-1.0) for how usable OCR/extracted text is.
    Counts the fraction of 'real word' tokens (alphabetic, length >= 3, or
    clean digit groups of 2+) against total tokens. Garbled OCR from a blurry
    photo produces mostly short noise fragments and scores low; clean text
    from a legible document scores high."""
    if not text or not text.strip():
        return 0.0

    tokens = text.split()
    if not tokens:
        return 0.0

    real_word_pattern = re.compile(r"^[A-Za-z]{3,}$|^\d{2,}$")
    real_count = sum(1 for t in tokens if real_word_pattern.match(t.strip(",.:;()[]{}\"'")))

    return real_count / len(tokens)


# Threshold tuned against two real samples: a badly blurred phone photo of a
# PAN card scored ~0.19, a clearly-legible document scored ~0.87. 0.3 sits
# safely between the two — adjust if real documents start landing near this
# boundary and getting mis-flagged either way.
QUALITY_THRESHOLD = 0.3

LOW_QUALITY_NOTE = "Document image quality is low — consider re-uploading a clearer photo or scan"


def check_document_quality(text: str, extracted_fields: dict, review_fields: set) -> str | None:
    """Flag likely image-quality problems by combining two signals:
    1. OCR text itself looks like noise (low real-word ratio)
    2. The final result is sparse — few fields extracted overall, or most
       of this module's review-flagged fields are specifically missing
    Only flags when BOTH signals agree, so a document where the LLM's
    vision reading succeeded despite poor OCR text isn't wrongly flagged."""
    quality_score = assess_text_quality(text)

    is_sparse = len(extracted_fields) <= 3
    missing_review_fields = [f for f in review_fields if f not in extracted_fields]
    review_mostly_missing = bool(review_fields) and len(missing_review_fields) >= len(review_fields) * 0.7

    if quality_score < QUALITY_THRESHOLD and (is_sparse or review_mostly_missing):
        return LOW_QUALITY_NOTE

    return None
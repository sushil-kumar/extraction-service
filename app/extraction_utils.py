import re

PLACEHOLDER_VALUES = {
    "not mentioned", "not available", "not found", "not visible",
    "not present", "not applicable", "n/a", "na", "none", "nil",
    "unknown", "-", "--", "not specified", "not given", "not stated",
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
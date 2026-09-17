from app.master_schema import REVIEW_RECOMMENDED_FIELDS

# Common "field not found" phrases models sometimes emit instead of
# omitting the field entirely, as instructed. Filtered out post-parse
# as a safety net — don't rely on prompt instructions alone.
PLACEHOLDER_VALUES = {
    "not mentioned", "not available", "not found", "not visible",
    "not present", "not applicable", "n/a", "na", "none", "nil",
    "unknown", "-", "--", "not specified", "not given", "not stated",
}


def is_placeholder_value(value) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False  # non-string values (e.g. subjects_marks lists) pass through untouched
    cleaned = value.strip().lower()
    return cleaned == "" or cleaned in PLACEHOLDER_VALUES


def filter_placeholders(extracted_fields: dict, confidence: dict) -> tuple[dict, dict]:
    """Remove any field whose value is a placeholder/not-found phrase."""
    clean_fields = {}
    clean_confidence = {}
    for field, value in extracted_fields.items():
        if not is_placeholder_value(value):
            clean_fields[field] = value
            clean_confidence[field] = confidence.get(field, 0.0)
    return clean_fields, clean_confidence

def get_fields_requiring_review(extracted_fields: dict) -> list[str]:
    """Fields present in the result that are conventionally flagged for manual
    review, regardless of the LLM's own reported confidence."""
    return [field for field in extracted_fields if field in REVIEW_RECOMMENDED_FIELDS]

def validate_subject_marks_sum(extracted_fields: dict) -> str | None:
    """Cross-check subject-wise marks against the reported total. Returns a
    warning string if they don't reconcile — doesn't fix anything, just flags
    it, since we can't know which side (total vs subject list) is wrong."""
    subjects = extracted_fields.get("subjects_marks")
    total = extracted_fields.get("total_marks")
    if not subjects or not total:
        return None

    try:
        subject_sum = sum(
            float(s["marks_obtained"]) for s in subjects
            if str(s.get("marks_obtained", "")).replace(".", "", 1).isdigit()
        )
        reported_total = float(total)
    except (ValueError, TypeError, KeyError):
        return None

    if abs(subject_sum - reported_total) > 1:  # small tolerance for rounding
        return f"Subject marks sum to {subject_sum:.0f} but total_marks reports {reported_total:.0f} — possible missing subject or OCR/extraction error"

    return None
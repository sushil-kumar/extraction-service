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
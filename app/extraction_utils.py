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
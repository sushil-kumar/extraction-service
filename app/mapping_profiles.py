"""
Each profile defines which master fields a specific target form needs,
and what to rename them to in the final DTO.
"""

STUDENT_ADMISSION_FORM_PROFILE = {
    "name": "candidate_name",
    "dateOfBirth": "date_of_birth",
    "rollNumber": "roll_number",
    "fatherName": "father_name",
    "address": "address",
}

MARKSHEET_RECORD_PROFILE = {
    "studentName": "candidate_name",
    "motherName": "mother_name",
    "seatNumber": "seat_number",
    "centreNumber": "centre_number",
    "examMonthYear": "exam_month_year",
    "percentage": "percentage",
    "totalMarks": "total_marks",
    "result": "result",
}

PROFILES = {
    "student_admission_form": STUDENT_ADMISSION_FORM_PROFILE,
    "marksheet_record": MARKSHEET_RECORD_PROFILE,
}

def apply_mapping(extracted_fields: dict, confidence: dict, profile_name: str) -> dict:
    """Select + rename only the fields a given target form cares about."""
    profile = PROFILES.get(profile_name)
    if not profile:
        raise ValueError(f"Unknown mapping profile: {profile_name}")

    mapped_fields = {}
    mapped_confidence = {}

    for target_key, master_key in profile.items():
        if master_key in extracted_fields:
            mapped_fields[target_key] = extracted_fields[master_key]
            mapped_confidence[target_key] = confidence.get(master_key, 0.0)

    return {"fields": mapped_fields, "confidence": mapped_confidence}
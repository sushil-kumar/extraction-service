MASTER_SCHEMA = {
    "candidate_name": "Full name of the person as printed on the document",
    "father_name": "Father's or guardian's name",
    "mother_name": "Mother's name",
    "date_of_birth": "Date of birth, normalized to YYYY-MM-DD",
    "gender": "Gender as stated on the document",
    "address": "Full residential address if given as a single labeled field",
    "village": "Village name, if mentioned (common in caste/domicile certificates)",
    "district": "District name",
    "state": "State name",

    "roll_number": "Student roll or enrollment number",
    "seat_number": "Exam seat number",
    "centre_number": "Exam centre number",
    "school_number": "School/college code or number",
    "board_name": "Examining board or university name",
    "stream": "Academic stream (Science/Commerce/Arts)",

    "exam_month_year": "Month and year of the examination",
    # Included here (with description) purely so the model is prompted to notice
    # subject-wise marks exist at all — empirically, omitting this entirely from
    # MASTER_SCHEMA made the model skip subject extraction. It is still excluded
    # from field_list in gemini_extractor.py / ollama_extractor.py (filtered by
    # key name) and from the actual 'fields' output (stripped via SUBJECT_FIELD_ALIASES
    # in ollama_extractor.py) — real subject data always comes from the separate
    # 'subject_wise_marks' schema array or the fallback recovery parser, never from
    # this key directly. Do not add a second/duplicate key for the same concept.
    "subject_wise_marks": "Subject-wise marks, including marks obtained and maximum marks per subject — extracted separately as a structured list, not a single value",
    "total_marks": "Total marks obtained out of maximum",
    "percentage": "Overall percentage",
    "result": "PASS/FAIL or grade result",

    "caste": "Caste or community name",
    "caste_category": "Caste category — OBC/SC/ST/general etc.",
    "certificate_number": "Certificate or statement number",
    "certificate_serial_number": "Serial number (Sr. No.) on caste/community certificates",

    "issue_date": "Date the document was issued",
    "issuing_authority": "Authority or body that issued the document",
    "issuing_place": "Place where the certificate was issued (e.g. city named at bottom of certificate)",
    "document_number": "Any ID/document/reference number printed on it",
}

REVIEW_RECOMMENDED_FIELDS = {
    "document_number",
    "certificate_serial_number",
    "certificate_number",
    "roll_number",
    "seat_number",
    "centre_number",
    "school_number",
    "date_of_birth",
    "issue_date",
}
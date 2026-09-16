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
    "subjects_marks": "Subject-wise marks — extracted separately as a structured list",
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
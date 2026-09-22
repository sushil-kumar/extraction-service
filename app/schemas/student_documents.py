MASTER_SCHEMA = {
    "document_type": "Classify this document as one of: marksheet, caste_certificate, "
                  "leaving_certificate, id_card, domicile_certificate, income_certificate, "
                  "aadhaar_card, pan_card, other. Always include this field — pick the single best match.",

    "candidate_name": "Full name of the person as printed on the document",
    "father_name": "Father's or guardian's name",
    "mother_name": "Mother's name",
    "date_of_birth": "Date of birth, normalized to YYYY-MM-DD",
    "gender": "Gender as stated on the document",
    "address": "Full residential address if given as a single labeled field",
    "village": "Village name, if mentioned (common in caste/domicile certificates)",
    "taluka": "Taluka/tehsil (sub-district administrative division), often abbreviated 'Tal.' — common on Maharashtra documents, distinct from district",
    "district": "District name",
    "state": "State name",
    "place_of_birth": "Place of birth (town/village), as distinct from current address",
    "nationality": "Nationality as stated on the document",

    "roll_number": "Student roll or enrollment number",
    "seat_number": "Exam seat number",
    "centre_number": "Exam centre number",
    "school_number": "School/college code or number",
    "board_name": "Examining board or university name",
    "stream": "Academic stream (Science/Commerce/Arts)",
    "last_institution_attended": "Name of the school/college last attended, as stated on a leaving/transfer certificate",
    "date_of_admission": "Date the student was admitted to the institution",
    "progress": "Academic progress remark (e.g. Good/Average/Excellent) on a leaving certificate",
    "conduct": "Conduct remark (e.g. Good/Satisfactory) on a leaving certificate",
    "date_of_leaving": "Date the student left/was relieved from the institution",
    "reason_of_leaving": "Stated reason for leaving the institution (e.g. Course completed, Transfer)",
    "remarks": "Any additional remarks noted on the document",

    "exam_month_year": "Month and year of the examination",
    "subject_wise_marks": "Subject-wise marks, including marks obtained and maximum marks per subject — extracted separately as a structured list, not a single value",
    "total_marks": "Total marks OBTAINED (not the maximum possible). On a marksheet's 'Total "
               "Marks' row, TWO numbers usually appear side by side — the maximum (e.g. "
               "'600') and the actual total obtained (e.g. '398') — with the obtained total "
               "confirmed by a spelled-out word form next to it (e.g. 'Three Hundred and "
               "Ninetyeight'). Always extract the obtained total, using the word form to "
               "verify which number is correct — never the maximum.",
    "percentage": "Overall percentage",
    "result": "PASS/FAIL or grade result",

    "caste": "Caste or community name",
    "caste_category": "Caste category — OBC/SC/ST/general etc.",
    "certificate_number": "Certificate or statement number",
    "certificate_serial_number": "Serial number (Sr. No.) on caste/community certificates",
    "registration_number": "Registration number and/or year printed on a leaving/transfer certificate",

    "issue_date": "Date the document was issued",
    "issuing_authority": "Authority or body that issued the document",
    "issuing_place": "Place where the certificate was issued (e.g. city named at bottom of certificate)",
    "document_number": "Any ID/document/reference number printed on it",

    "aadhaar_number": "The 12-digit UIDAI Aadhaar number specifically, printed as 4-4-4 digit "
                   "groups (e.g. '1234 5678 9012'), usually near the UIDAI logo/QR code. "
                   "Do NOT use this field's value for roll_number, document_number, or "
                   "certificate_number — those are separate fields. If the Aadhaar number is "
                   "partially masked/blacked out on the document (common for privacy, e.g. "
                   "showing only the last 4 digits), extract only what is actually visible — "
                   "do not guess or fill in the masked portion.",
    "pan_number": "10-character PAN number, format 5 letters + 4 digits + 1 letter (e.g. 'ABCDE1234F')",
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
    "registration_number",
    "date_of_admission",
    "date_of_leaving",
    "aadhaar_number",
    "pan_number",
}
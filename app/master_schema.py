"""
Master registry of every field we know how to extract, across all document types.
Extraction always runs against this full set (or a relevant subset) — 
individual forms then pick out what they need via a mapping profile.
"""

MASTER_SCHEMA = {
    # identity fields
    "candidate_name": "Full name of the person as printed on the document",
    "father_name": "Father's or guardian's name",
    "mother_name": "Mother's name",
    "date_of_birth": "Date of birth, normalized to YYYY-MM-DD",
    "gender": "Gender as stated on the document",
    "address": "Residential address",

    # academic/exam identifiers
    "roll_number": "Student roll or enrollment number",
    "seat_number": "Exam seat number",
    "centre_number": "Exam centre number",
    "school_number": "School/college code or number",
    "board_name": "Examining board or university name",
    "stream": "Academic stream (Science/Commerce/Arts)",

    # exam/marksheet specific
    "exam_month_year": "Month and year of the examination",
    "subjects_marks": "List of subjects with marks obtained per subject",
    "total_marks": "Total marks obtained out of maximum",
    "percentage": "Overall percentage",
    "result": "PASS/FAIL or grade result",
    "certificate_number": "Certificate or statement number",

    # generic document metadata
    "issue_date": "Date the document was issued",
    "issuing_authority": "Authority or body that issued the document",
    "document_number": "Any ID/document/reference number printed on it",
}
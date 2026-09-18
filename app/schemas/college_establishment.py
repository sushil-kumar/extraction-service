COLLEGE_ESTABLISHMENT_SCHEMA = {
    "document_type": "Classify as one of: land_record, society_registration, "
                      "noc_certificate, building_plan, other. Always include this field.",

    "survey_number": "Survey/Gat number of the land parcel",
    "land_area": "Area of land, with unit (acres/hectares/sq.ft as stated)",
    "land_type": "Land classification (agricultural/non-agricultural/NA)",
    "land_owner_name": "Name(s) of the registered land owner(s)",
    "khata_number": "Khata/account number on the land record",
    "village": "Village where the land is located",
    "taluka": "Taluka of the land record",
    "district": "District of the land record",
    "state": "State of the land record",

    "society_name": "Registered name of the society/trust",
    "society_registration_number": "Registration number of the society",
    "society_registration_date": "Date the society was registered, normalized to YYYY-MM-DD",
    "registering_authority": "Authority that registered the society (e.g. Charity Commissioner, Registrar of Societies)",
    "society_address": "Registered address of the society",
    "society_type": "Type of registration (Public Trust, Society, Section 8 company, etc.)",

    "issue_date": "Date the document was issued",
    "document_number": "Any reference/document number printed on it",
}

REVIEW_RECOMMENDED_FIELDS = {
    "survey_number",
    "khata_number",
    "society_registration_number",
    "society_registration_date",
    "document_number",
}
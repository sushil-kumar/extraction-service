COLLEGE_ESTABLISHMENT_SCHEMA = {
    "document_type": "Classify as one of: land_record, society_registration, "
                      "noc_certificate, building_plan, other. Always include this field.",

    "pu_id": "PU-ID — a system-generated Property Unique ID printed at the top of a 7/12 "
             "land record. This is NOT the survey number — do not confuse the two.",
    "survey_number": "भूमापन क्रमांक व उपविभाग / गट क्रमांक व उपविभाग — the actual survey/Gat "
                      "number and subdivision (e.g. '209/A', '508'). The true land parcel "
                      "identifier, distinct from PU-ID.",
    "tenure_type": "भुधारणा पद्धती — land tenure classification (e.g. भोगवटादार वर्ग-१)",
    "village": "गाव — village where the land is located",
    "taluka": "तालुका — taluka of the land record",
    "district": "जिल्हा — district of the land record. Read the printed word carefully; "
                "do not substitute a different, more familiar district name.",
    "state": "State of the land record",

    "total_area": "एकूण क्षेत्र — total land area in Hectare.Are.SqM format (e.g. '5.55.00'), "
                  "from the एकूण क्षेत्र row specifically. NOT the आकारणी (assessment) figure.",
    "total_assessment": "आकारणी — total tax/assessment figure, distinct from area",
    "land_type": "Land classification — अकृषिक (non-agricultural/NA) or शेती/जिरायत/बागायत "
                 "(agricultural, dry or irrigated)",

    "encumbrances": "इतर अधिकार — any mortgage, bank charge, loan, or other encumbrance noted "
                     "against the land, including the lender's name and loan amount if stated. "
                     "Copy this note's substance in full — it is legally significant for "
                     "determining if the land is free of claims.",
    "pending_mutation": "प्रलंबित फेरफार — whether a mutation entry is currently pending",
    "last_mutation_number": "शेवटचा फेरफार क्रमांक — most recent mutation (फेरफार) entry number",
    "last_mutation_date": "date of the most recent mutation entry, normalized to YYYY-MM-DD",

    "society_name": "Registered name of the society/trust",
    "society_registration_number": "Registration number of the society",
    "society_registration_date": "Date the society was registered, normalized to YYYY-MM-DD",
    "registering_authority": "Authority that registered the society (e.g. Charity Commissioner)",
    "society_address": "Registered address of the society",
    "society_type": "Type of registration (Public Trust, Society, Section 8 company, etc.)",

    "land_owners": "List of all landholders (खातेदार/भोगवटादार) in the ownership table, each "
                    "with their own khata number, name, area, and assessment — extracted as a "
                    "structured list. A land record commonly lists multiple co-owners across "
                    "separate rows; do not collapse them into one field.",

    "issue_date": "Date the document itself was issued/digitally signed",
    "document_number": "Any reference/document number printed on it, distinct from PU-ID and survey number",
}

REVIEW_RECOMMENDED_FIELDS = set(COLLEGE_ESTABLISHMENT_SCHEMA.keys()) - {"document_type"}
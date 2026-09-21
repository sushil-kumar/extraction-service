from app.schemas.student_documents import (
    MASTER_SCHEMA as STUDENT_DOCUMENTS_SCHEMA,
    REVIEW_RECOMMENDED_FIELDS as STUDENT_REVIEW_FIELDS,
)
from app.schemas.college_establishment import (
    COLLEGE_ESTABLISHMENT_SCHEMA,
    REVIEW_RECOMMENDED_FIELDS as COLLEGE_REVIEW_FIELDS,
)

MODULE_SCHEMAS = {
    "student_documents": {
        "schema": STUDENT_DOCUMENTS_SCHEMA,
        "review_fields": STUDENT_REVIEW_FIELDS,
        "use_regex_fallback": True,
        "array_field": "subject_wise_marks",
    },
    "college_establishment": {
        "schema": COLLEGE_ESTABLISHMENT_SCHEMA,
        "review_fields": COLLEGE_REVIEW_FIELDS,
        "use_regex_fallback": False,
        "array_field": "land_owners",
    },
}

DEFAULT_MODULE = "student_documents"


def get_module_config(module_name: str | None) -> dict:
    module_name = module_name or DEFAULT_MODULE
    if module_name not in MODULE_SCHEMAS:
        raise ValueError(f"Unknown module: {module_name}. Valid modules: {list(MODULE_SCHEMAS.keys())}")
    return MODULE_SCHEMAS[module_name]
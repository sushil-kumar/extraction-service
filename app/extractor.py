import logging
from app.ocr import get_document_text, pdf_to_image_bytes
from app.rules_extractor import extract_with_rules
from app.mapping_profiles import apply_mapping
from app.config import settings
from app.extraction_utils import filter_placeholders, get_fields_requiring_review, validate_subject_marks_sum, clean_subjects_marks

logger = logging.getLogger(__name__)


async def extract_fields_from_bytes(file_bytes: bytes, content_type: str, profile_name: str | None = None) -> dict:
    text = get_document_text(file_bytes, content_type)

    extracted = {}
    confidence = {}
    note = None
    llm_fields_raw = None
    llm_confidence_raw = None
    llm_succeeded = False

    if settings.llm_available:
        image_bytes = None
        media_type = None
        if not text and content_type == "application/pdf":
            image_bytes = pdf_to_image_bytes(file_bytes)
            media_type = "image/png"
        elif content_type in ("image/jpeg", "image/png", "image/webp"):
            image_bytes = file_bytes
            media_type = content_type

        try:
            if settings.llm_provider == "gemini":
                from app.gemini_extractor import extract_with_gemini
                llm_result = await extract_with_gemini(text, image_bytes, media_type)
            elif settings.llm_provider == "ollama":
                from app.ollama_extractor import extract_with_ollama
                if image_bytes is None:
                    image_bytes = pdf_to_image_bytes(file_bytes)
                    media_type = "image/png"
                llm_result = await extract_with_ollama(image_bytes, media_type)
            else:
                from app.llm_extractor import extract_with_llm
                llm_result = await extract_with_llm(text, image_bytes, media_type)

            llm_fields_raw = llm_result["extracted_fields"]
            llm_confidence_raw = llm_result["confidence"]

            if llm_fields_raw:
                extracted = dict(llm_fields_raw)
                confidence = dict(llm_confidence_raw)
                llm_succeeded = True

        except Exception as e:
            logger.exception(f"LLM extraction failed ({settings.llm_provider})")  # logger.exception includes full traceback
            note = str(e)
    else:
        note = f"LLM not configured for provider '{settings.llm_provider}'"

    if not llm_succeeded:
        logger.info("LLM extraction unavailable/failed — falling back to regex-based extraction")
        rules_result = extract_with_rules(text)
        for field, value in rules_result["extracted_fields"].items():
            if field not in extracted:
                extracted[field] = value
                confidence[field] = rules_result["confidence"][field]

    extracted, confidence = filter_placeholders(extracted, confidence)

    extracted = clean_subjects_marks(extracted)
    if "subjects_marks" not in extracted:
        confidence.pop("subjects_marks", None)  # keep confidence dict in sync

    # cross-check subject marks against reported total, append to note if mismatched
    marks_warning = validate_subject_marks_sum(extracted)
    if marks_warning:
        note = f"{note}; {marks_warning}" if note else marks_warning

    if profile_name:
        mapped = apply_mapping(extracted, confidence, profile_name)
        return {
            "extracted_fields": mapped["fields"], "confidence": mapped["confidence"],
            "note": note, "llm_fields": llm_fields_raw, "llm_confidence": llm_confidence_raw,
            "fields_requiring_review": get_fields_requiring_review(mapped["fields"]),
        }

    return {
        "extracted_fields": extracted, "confidence": confidence, "note": note,
        "llm_fields": llm_fields_raw, "llm_confidence": llm_confidence_raw,
        "fields_requiring_review": get_fields_requiring_review(extracted),
    }


def merge_document_results(results: list[dict]) -> dict:
    """Merge extraction results from multiple documents. For each field,
    keep the value from whichever document reported it with the highest confidence."""
    merged_fields = {}
    merged_confidence = {}

    for result in results:
        for field, value in result["extracted_fields"].items():
            field_confidence = result["confidence"].get(field, 0.0)
            if field not in merged_fields or field_confidence > merged_confidence[field]:
                merged_fields[field] = value
                merged_confidence[field] = field_confidence

    return {"extracted_fields": merged_fields, "confidence": merged_confidence}
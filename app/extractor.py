import logging
from app.ocr import get_document_text, pdf_to_image_bytes
from app.rules_extractor import extract_with_rules
from app.mapping_profiles import apply_mapping
from app.config import settings
from app.schemas import get_module_config
from app.extraction_utils import (
    filter_placeholders, get_fields_requiring_review,
    validate_subject_marks_sum, clean_subjects_marks,
    deduplicate_identity_number, enforce_document_type_whitelist,
    normalize_document_type, check_document_quality
)

logger = logging.getLogger(__name__)

# Fields where LLM recall has proven unreliable enough (across many repeated
# test runs) that we always cross-check with regex, regardless of whether the
# LLM call succeeded — not just as a fallback when it fails outright.
ALWAYS_SUPPLEMENT_FIELDS = {"caste_category", "pan_number", "aadhaar_number"}
LOW_CONFIDENCE_THRESHOLD = 0.7


async def extract_fields_from_bytes(
    file_bytes: bytes, content_type: str,
    profile_name: str | None = None, module: str | None = None,
) -> dict:
    module_config = get_module_config(module)
    active_schema = module_config["schema"]
    active_review_fields = module_config["review_fields"]
    use_regex_fallback = module_config["use_regex_fallback"]
    array_field = module_config["array_field"]

    text = get_document_text(file_bytes, content_type)

    extracted = {}
    confidence = {}
    note = None
    llm_fields_raw = None
    llm_confidence_raw = None
    llm_succeeded = False

    rules_result = extract_with_rules(text) if (use_regex_fallback or ALWAYS_SUPPLEMENT_FIELDS) else None
    if use_regex_fallback and rules_result:
        extracted = dict(rules_result["extracted_fields"])
        confidence = dict(rules_result["confidence"])

    regex_quality_note = (
        check_document_quality(text, extracted, active_review_fields)
        if use_regex_fallback else None
    )
    regex_needs_llm = (
        not extracted
        or len(extracted) <= 3
        or any(score < LOW_CONFIDENCE_THRESHOLD for score in confidence.values())
        or regex_quality_note is not None
    )
    should_call_llm = not use_regex_fallback or regex_needs_llm

    if use_regex_fallback and regex_needs_llm and settings.llm_available:
        low_confidence_fields = {
            field: score for field, score in confidence.items()
            if score < LOW_CONFIDENCE_THRESHOLD
        }
        if not extracted:
            logger.info(
                "Regex extraction returned no fields; invoking %s LLM extraction",
                settings.llm_provider,
            )
        elif regex_quality_note:
            logger.info(
                "Regex extraction indicates low document quality (%s); invoking %s LLM extraction",
                regex_quality_note,
                settings.llm_provider,
            )
        elif len(extracted) <= 2:
            logger.info(
                "Regex extraction returned only %d fields i.e. (%s); invoking %s LLM extraction",
                len(extracted),
                ", ".join(extracted.keys()),
                settings.llm_provider,
            )
        else:
            logger.info(
                "Regex extraction confidence below %.2f for fields and scores %s; invoking %s LLM extraction",
                LOW_CONFIDENCE_THRESHOLD,
                low_confidence_fields,
                settings.llm_provider,
            )

    if should_call_llm and settings.llm_available:
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
                llm_result = await extract_with_gemini(text, image_bytes, media_type, active_schema, array_field)
            elif settings.llm_provider == "ollama":
                from app.ollama_extractor import extract_with_ollama
                if image_bytes is None:
                    image_bytes = pdf_to_image_bytes(file_bytes)
                    media_type = "image/png"
                llm_result = await extract_with_ollama(image_bytes, media_type, active_schema, array_field)
            else:
                from app.llm_extractor import extract_with_llm
                llm_result = await extract_with_llm(text, image_bytes, media_type)

            llm_fields_raw = llm_result["extracted_fields"]
            llm_confidence_raw = llm_result["confidence"]

            if llm_fields_raw:
                for field, value in llm_fields_raw.items():
                    llm_score = llm_confidence_raw.get(field, 0.0)
                    current_score = confidence.get(field, 0.0)
                    if field not in extracted or (
                        use_regex_fallback
                        and (
                            regex_quality_note is not None
                            or (
                                current_score < LOW_CONFIDENCE_THRESHOLD
                                and llm_score > current_score
                            )
                        )
                    ):
                        extracted[field] = value
                        confidence[field] = llm_score
                llm_succeeded = True

        except Exception as e:
            logger.exception(f"LLM extraction failed ({settings.llm_provider})")
            note = str(e)
    elif should_call_llm:
        note = f"LLM not configured for provider '{settings.llm_provider}'"

    if use_regex_fallback and not regex_needs_llm:
        logger.info("Regex extraction produced sufficiently confident results; skipping LLM extraction")
    elif not llm_succeeded and use_regex_fallback:
        logger.info("LLM extraction unavailable/failed — retaining regex-based extraction results")
    elif not llm_succeeded:
        logger.info("LLM extraction unavailable/failed and this module has no regex fallback — result will be empty")

    # always-on supplement: for specific known-flaky fields, cross-check with
    # regex even after a successful LLM call — only for fields that actually
    # belong to this module's schema, so we don't leak irrelevant fields
    # across modules (e.g. never inject caste_category into a land record)
    if rules_result:
        for field in ALWAYS_SUPPLEMENT_FIELDS:
            if field not in active_schema:
                continue
            if not extracted.get(field):
                if field in rules_result["extracted_fields"]:
                    extracted[field] = rules_result["extracted_fields"][field]
                    confidence[field] = rules_result["confidence"][field]

    extracted, confidence = filter_placeholders(extracted, confidence, schema=active_schema)
    extracted = clean_subjects_marks(extracted)
    extracted = deduplicate_identity_number(extracted)
    extracted = normalize_document_type(extracted)
    extracted, confidence = enforce_document_type_whitelist(extracted, confidence)

    if "subjects_marks" not in extracted:
        confidence.pop("subjects_marks", None)

    quality_note = check_document_quality(text, extracted, active_review_fields)
    if quality_note:
        note = f"{note}; {quality_note}" if note else quality_note

    marks_warning = validate_subject_marks_sum(extracted)
    if marks_warning:
        note = f"{note}; {marks_warning}" if note else marks_warning

    if profile_name:
        mapped = apply_mapping(extracted, confidence, profile_name)
        return {
            "extracted_fields": mapped["fields"], "confidence": mapped["confidence"],
            "note": note, "llm_fields": llm_fields_raw, "llm_confidence": llm_confidence_raw,
            "fields_requiring_review": get_fields_requiring_review(mapped["fields"], active_review_fields),
        }

    return {
        "extracted_fields": extracted, "confidence": confidence, "note": note,
        "llm_fields": llm_fields_raw, "llm_confidence": llm_confidence_raw,
        "fields_requiring_review": get_fields_requiring_review(extracted, active_review_fields),
    }


def merge_document_results(results: list[dict]) -> dict:
    merged_fields = {}
    merged_confidence = {}

    for result in results:
        for field, value in result["extracted_fields"].items():
            field_confidence = result["confidence"].get(field, 0.0)
            if field not in merged_fields or field_confidence > merged_confidence[field]:
                merged_fields[field] = value
                merged_confidence[field] = field_confidence

    return {"extracted_fields": merged_fields, "confidence": merged_confidence}
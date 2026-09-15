import logging
from app.ocr import get_document_text, pdf_to_image_bytes
from app.rules_extractor import extract_with_rules
from app.llm_extractor import extract_with_llm, ExtractionError, LLMNotConfiguredError
from app.mapping_profiles import apply_mapping
from app.config import settings

logger = logging.getLogger(__name__)

async def extract_fields_from_bytes(file_bytes: bytes, content_type: str, profile_name: str | None = None) -> dict:
    text = get_document_text(file_bytes, content_type)

    # Step 1: always try free rules-based extraction first — works without any API key
    rules_result = extract_with_rules(text)
    extracted = rules_result["extracted_fields"]
    confidence = rules_result["confidence"]
    note = None

    # Step 2: only attempt the LLM if it's actually configured
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
            llm_result = await extract_with_llm(text=text if text else None, image_bytes=image_bytes, media_type=media_type)
            # LLM result fills gaps / overrides low-confidence regex matches
            for field, value in llm_result["extracted_fields"].items():
                if field not in extracted or confidence.get(field, 0) < 0.75:
                    extracted[field] = value
                    confidence[field] = llm_result["confidence"].get(field, 0.7)
        except (LLMNotConfiguredError, ExtractionError) as e:
            logger.warning(f"LLM extraction skipped/failed: {e}")
            note = str(e)
    else:
        logger.info("LLM not configured — returning rules-based extraction only")
        note = "LLM not configured — showing free/regex extraction only"

    if profile_name:
        mapped = apply_mapping(extracted, confidence, profile_name)
        return {"extracted_fields": mapped["fields"], "confidence": mapped["confidence"], "note": note}

    return {"extracted_fields": extracted, "confidence": confidence, "note": note}
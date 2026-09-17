import time
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException
from app.config import settings
from app.extractor import extract_fields_from_bytes, merge_document_results
from app.models import (
    ExtractionResponse, HealthResponse,
    BatchExtractionResponse, DocumentExtractionResult,
)

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="Document Extraction Service", version="1.0.0")

ALLOWED_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = settings.max_file_size_mb * 1024 * 1024
MAX_FILES_PER_BATCH = 5


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="UP", service="document-extraction-service")


@app.post("/extract", response_model=ExtractionResponse)
async def extract(file: UploadFile = File(...), profile: str | None = None):
    start_time = time.perf_counter()

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported content type: {file.content_type}")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File exceeds max size of {settings.max_file_size_mb}MB")
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    result = await extract_fields_from_bytes(file_bytes, file.content_type, profile_name=profile)

    elapsed = time.perf_counter() - start_time
    logger.info(f"[TIMING] /extract for '{file.filename}' completed in {elapsed:.2f}s (provider={settings.llm_provider})")

    return ExtractionResponse(
        extractedFields=result["extracted_fields"],
        confidence=result["confidence"],
        llmFields=result.get("llm_fields"),
        llmConfidence=result.get("llm_confidence"),
        fieldsRequiringReview=result.get("fields_requiring_review", []),
        status="SUCCESS" if result["extracted_fields"] else "FAILED",
        note=result.get("note"),
    )


@app.post("/extract-batch", response_model=BatchExtractionResponse)
async def extract_batch(files: list[UploadFile] = File(...), profile: str | None = None):
    start_time = time.perf_counter()
    if len(files) == 0:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > MAX_FILES_PER_BATCH:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_FILES_PER_BATCH} documents per request")

    per_document_results = []
    raw_results_for_merge = []

    for file in files:
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            per_document_results.append(DocumentExtractionResult(
                filename=file.filename, extractedFields={}, confidence={},
                status="FAILED", note=f"Unsupported content type: {file.content_type}",
            ))
            continue

        file_bytes = await file.read()

        if len(file_bytes) > MAX_FILE_SIZE:
            per_document_results.append(DocumentExtractionResult(
                filename=file.filename, extractedFields={}, confidence={},
                status="FAILED", note=f"File exceeds max size of {settings.max_file_size_mb}MB",
            ))
            continue

        if len(file_bytes) == 0:
            per_document_results.append(DocumentExtractionResult(
                filename=file.filename, extractedFields={}, confidence={},
                status="FAILED", note="Empty file",
            ))
            continue

        try:
            result = await extract_fields_from_bytes(file_bytes, file.content_type)
            per_document_results.append(DocumentExtractionResult(
                filename=file.filename,
                extractedFields=result["extracted_fields"],
                confidence=result["confidence"],
                status="SUCCESS" if result["extracted_fields"] else "FAILED",
                note=result.get("note"),
            ))
            raw_results_for_merge.append(result)
        except Exception as e:
            logger.exception(f"Failed to extract {file.filename}")
            per_document_results.append(DocumentExtractionResult(
                filename=file.filename, extractedFields={}, confidence={},
                status="FAILED", note=str(e),
            ))

    merged = merge_document_results(raw_results_for_merge)

    # apply the target-form mapping profile to the MERGED result, not per-document
    if profile:
        from app.mapping_profiles import apply_mapping
        mapped = apply_mapping(merged["extracted_fields"], merged["confidence"], profile)
        merged_fields, merged_confidence = mapped["fields"], mapped["confidence"]
    else:
        merged_fields, merged_confidence = merged["extracted_fields"], merged["confidence"]

    overall_status = "SUCCESS" if merged_fields else "FAILED"

    elapsed = time.perf_counter() - start_time
    logger.info(f"[TIMING] /extract-batch for {len(files)} file(s) completed in {elapsed:.2f}s (provider={settings.llm_provider})")

    return BatchExtractionResponse(
        mergedFields=merged_fields,
        mergedConfidence=merged_confidence,
        perDocument=per_document_results,
        status=overall_status,
    )
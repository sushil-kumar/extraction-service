import logging
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from app.config import settings
from app.extractor import extract_fields_from_bytes
from app.llm_extractor import ExtractionError
from app.models import ExtractionResponse, HealthResponse

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="Document Extraction Service", version="1.0.0")

ALLOWED_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = settings.max_file_size_mb * 1024 * 1024


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="UP", service="document-extraction-service")


@app.post("/extract", response_model=ExtractionResponse)
async def extract(file: UploadFile = File(...), profile: str | None = None):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported content type: {file.content_type}")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File exceeds max size of {settings.max_file_size_mb}MB")
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    result = await extract_fields_from_bytes(file_bytes, file.content_type, profile_name=profile)

    note = result.get("note")
    status = "SKIPPED" if note and "skipped" in note.lower() else ("SUCCESS" if result["extracted_fields"] else "FAILED")

    return ExtractionResponse(
        extractedFields=result["extracted_fields"],
        confidence=result["confidence"],
        status=status,
        note=note,
    )
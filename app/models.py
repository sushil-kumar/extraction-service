from pydantic import BaseModel
from typing import Optional


class ExtractionResponse(BaseModel):
    extractedFields: dict          # final merged result (regex + LLM)
    confidence: dict
    llmFields: Optional[dict] = None       # raw LLM-only fields, unmerged, for debugging/visibility
    llmConfidence: Optional[dict] = None
    status: str                     # SUCCESS | FAILED
    errorMessage: Optional[str] = None
    note: Optional[str] = None


class DocumentExtractionResult(BaseModel):
    filename: str
    extractedFields: dict
    confidence: dict
    status: str                     # SUCCESS | FAILED
    note: Optional[str] = None


class BatchExtractionResponse(BaseModel):
    mergedFields: dict
    mergedConfidence: dict
    perDocument: list[DocumentExtractionResult]
    status: str                     # SUCCESS | FAILED


class HealthResponse(BaseModel):
    status: str
    service: str
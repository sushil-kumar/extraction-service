from pydantic import BaseModel
from typing import Optional


class ExtractionResponse(BaseModel):
    extractedFields: dict
    confidence: dict
    llmFields: Optional[dict] = None
    llmConfidence: Optional[dict] = None
    fieldsRequiringReview: list[str] = []   # field names the student should double-check
    status: str
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
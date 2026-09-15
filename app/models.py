from pydantic import BaseModel
from typing import Optional

class ExtractionResponse(BaseModel):
    extractedFields: dict
    confidence: dict
    status: str  # SUCCESS | FAILED | SKIPPED
    errorMessage: Optional[str] = None
    note: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    service: str
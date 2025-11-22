# app/models.py
import hashlib
from enum import Enum
from pydantic import BaseModel
from typing import Optional, List


class DocumentResponse(BaseModel):
    page_content: str
    metadata: dict


class DocumentModel(BaseModel):
    page_content: str
    metadata: Optional[dict] = {}

    def generate_digest(self):
        hash_obj = hashlib.md5(self.page_content.encode())
        return hash_obj.hexdigest()


class StoreDocument(BaseModel):
    filepath: str
    filename: str
    file_content_type: str
    file_id: str


class QueryRequestBody(BaseModel):
    query: str
    file_id: str
    k: int = 4
    entity_id: Optional[str] = None


class CleanupMethod(str, Enum):
    incremental = "incremental"
    full = "full"


class QueryMultipleBody(BaseModel):
    query: str
    file_ids: List[str]
    k: int = 4


class ChatRequestBody(BaseModel):
    """Request body for RAG chat with LLM response."""
    query: str
    file_id: str
    k: int = 4
    entity_id: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1500
    system_prompt: Optional[str] = None


class ChatResponse(BaseModel):
    """Response from RAG chat endpoint."""
    answer: str
    query: str
    file_id: str
    sources_used: int
    model: str

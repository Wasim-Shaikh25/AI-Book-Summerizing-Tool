import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BookMetadata(BaseModel):
    """
    Represents the high-level metadata for a processed book or PDF.
    Used for future filtering by subject or source file.
    """
    book_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    subject: str = "unknown"
    source_file_name: str
    total_pages: int

class TopicKnowledge(BaseModel):
    """
    Represents the granular knowledge extracted for a specific topic.
    Designed for Question-Answering and semantic retrieval.
    """
    topic_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    book_id: str
    topic: str
    subtopic: Optional[str] = None
    source_page: Optional[int] = None
    importance_score: float = 0.0 # 0.0 to 1.0
    
    # Content fields
    raw_content: str
    
    # Metadata for retrieval and processing
    topic_type: str = "general" # core_concept, sub_concept, etc.
    embedding: Optional[List[float]] = None # For future semantic search
    metadata: Dict[str, Any] = Field(default_factory=dict)

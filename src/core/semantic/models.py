from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class ExplanationDepth(BaseModel):
    definition: bool = False
    intuition: bool = False
    derivation: bool = False
    examples: str = "none"  # none | brief | full
    proof: bool = False
    allowed_expansion: str = "rephrase_only" # rephrase_only | enhance | compress

class BlueprintNode(BaseModel):
    title: str
    level: int  # 1 for Chapter, 2 for Section, 3 for Topic
    derived_topic_id: Optional[str] = None
    original_structure_path: Optional[str] = None  # e.g., "Chapter 3 > Section 3.2 > Topic 3.2.1"
    usage_type: str = "referenced_only"  # explained | contextual | referenced_only
    explanation_depth: ExplanationDepth = Field(default_factory=ExplanationDepth)
    max_source_extent: Optional[str] = None  # e.g., "3 paragraphs" or "2 pages"
    allowed_expansion: str = "rephrase_only"  # rephrase_only | enhance | compress
    concept_ids: List[str] = Field(default_factory=list) # Maps to SourceBlueprint topic_ids
    children: List['BlueprintNode'] = Field(default_factory=list)

class SourceBlueprint(BaseModel):
    """
    Authoritative, Book-Faithful blueprint.
    Preserves original book hierarchy: Chapter -> Section -> Topic.
    Built ONLY from reading book content.
    Immutable after creation.
    """
    book_id: str
    hierarchy: List[BlueprintNode]
    concepts: List[Dict[str, Any]]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1.0"

    class Config:
        frozen = True  # Makes the model immutable

class DerivedBlueprint(BaseModel):
    """
    Authorial, User-Facing blueprint.
    Generated ONLY from SourceBlueprint.
    Must NEVER read raw PDF text.
    """
    source_blueprint_id: str
    book_id: str
    hierarchy: List[BlueprintNode]
    concepts: List[Dict[str, Any]]
    authorial_intent: Optional[str] = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1.0"

class ConceptTermRecord(BaseModel):
    """
    Flat term record discovered by ConceptDiscoveryAgent.
    """
    term: str
    classification: str  # EXPLAINED_CONCEPT | REFERENCED_ONLY | DEPENDENCY_ONLY
    verbatim_evidence: Optional[str] = None
    source_location: Optional[str] = None
    confidence: float = 0.0

# Handle recursive model definition
BlueprintNode.update_forward_refs()

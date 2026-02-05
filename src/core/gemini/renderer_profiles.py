from pydantic import BaseModel
from enum import Enum
from typing import Dict

class ExampleHandling(str, Enum):
    KEEP_ALL = "keep_all"
    COMPRESS_OR_DROP_LOW_RELEVANCE = "compress_or_drop_low_relevance"

class ContentFreedom(str, Enum):
    ALLOW_ENHANCEMENT = "allow_enhancement"
    RESTRICTED = "restricted"
    FORBIDDEN = "forbidden"

class RendererProfile(BaseModel):
    name: str
    bullet_ratio: str # e.g., "high", "very_high", "low"
    prose_ratio: str # e.g., "high", "medium", "low"
    example_handling: ExampleHandling
    content_freedom: ContentFreedom

# Define the canonical profiles
PROFILES: Dict[str, RendererProfile] = {
    "BOOK_MODE": RendererProfile(
        name="BOOK / NOVEL MODE",
        bullet_ratio="low",
        prose_ratio="high",
        example_handling=ExampleHandling.KEEP_ALL,
        content_freedom=ContentFreedom.ALLOW_ENHANCEMENT
    ),
    "NOTES_MODE": RendererProfile(
        name="NOTES MODE",
        bullet_ratio="high",
        prose_ratio="medium",
        example_handling=ExampleHandling.KEEP_ALL,
        content_freedom=ContentFreedom.RESTRICTED
    ),
    "EXAM_NOTES_MODE": RendererProfile(
        name="EXAM NOTES MODE",
        bullet_ratio="very_high",
        prose_ratio="low",
        example_handling=ExampleHandling.COMPRESS_OR_DROP_LOW_RELEVANCE,
        content_freedom=ContentFreedom.FORBIDDEN
    )
}

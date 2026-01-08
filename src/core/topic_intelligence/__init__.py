"""
Topic Intelligence Module
Responsible for advanced topic management, including normalization, deduplication,
classification, and relationship mapping.
"""

from .topic_normalizer import TopicNormalizer
from .topic_deduplicator import TopicDeduplicator
from .topic_classifier import TopicClassifier
from .topic_relationships import TopicRelationshipMapper
from .topic_registry import TopicRegistry

__all__ = [
    "TopicNormalizer",
    "TopicDeduplicator",
    "TopicClassifier",
    "TopicRelationshipMapper",
    "TopicRegistry",
]

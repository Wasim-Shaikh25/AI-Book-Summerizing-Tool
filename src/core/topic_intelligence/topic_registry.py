import logging
import json
import os
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class TopicRegistry:
    """
    Central registry to track explained topics and prevent redundancy.
    Persists state to a JSON file.
    """
    def __init__(self, storage_path: str = "output/topic_registry.json"):
        self.storage_path = storage_path
        self.registry: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        """Loads the registry from the JSON file if it exists."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    self.registry = json.load(f)
                logger.info(f"Loaded topic registry from {self.storage_path} with {len(self.registry)} topics.")
            except Exception as e:
                logger.error(f"Failed to load topic registry: {e}")
                self.registry = {}

    def _save(self):
        """Saves the current registry state to the JSON file."""
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(self.registry, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved topic registry to {self.storage_path}")
        except Exception as e:
            logger.error(f"Failed to save topic registry: {e}")

    def register_topic(self, topic_name: str, explanation_depth: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Registers a topic as explained.
        """
        self.registry[topic_name.lower()] = {
            "canonical_name": topic_name,
            "explanation_depth": explanation_depth,
            "metadata": metadata or {},
            "explained": True
        }
        self._save()
        logger.info(f"Registered topic: {topic_name} (Depth: {explanation_depth})")

    def is_explained(self, topic_name: str) -> bool:
        """
        Checks if a topic has already been explained.
        """
        return topic_name.lower() in self.registry

    def get_explanation_depth(self, topic_name: str) -> Optional[str]:
        """
        Returns the explanation depth of a registered topic.
        """
        topic_data = self.registry.get(topic_name.lower())
        return topic_data.get("explanation_depth") if topic_data else None

    def clear(self):
        """Clears the registry."""
        self.registry = {}
        if os.path.exists(self.storage_path):
            os.remove(self.storage_path)
        logger.info("Topic registry cleared.")

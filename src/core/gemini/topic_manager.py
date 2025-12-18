import re
from typing import List, Dict, Any
from fuzzywuzzy import fuzz # For fuzzy matching topic names

class TopicManager:
    """
    Manages the canonical list of topics, matching chunks to topics,
    and collecting information for each topic.
    """
    def __init__(self, embedder, summarizer):
        self.canonical_topics: List[Dict[str, Any]] = []
        self.embedder = embedder # To embed topic names and chunk content
        self.summarizer = summarizer # To extract facts and rewrite topics
        self.topic_embeddings = None # Stores embeddings of canonical topic names

    def canonicalize_topics(self, master_brain: str):
        """
        Extracts a canonical list of topics from the master brain.
        Each topic has topic_id, topic_name, written=false, collected_points=[].
        """
        # Use the summarizer to extract a list of distinct topics from the master brain
        # This prompt needs to be carefully crafted to get a good list of canonical topics
        topic_list_raw = self.summarizer.extract_canonical_topics_from_master_brain(master_brain)
        
        # Parse the raw topic list into the desired structure
        # Assuming topic_list_raw is a newline-separated string of topic names
        for i, topic_name in enumerate(topic_list_raw.split('\n')):
            topic_name = topic_name.strip()
            if topic_name:
                topic_id = self._normalize_topic_name(topic_name)
                self.canonical_topics.append({
                    "topic_id": topic_id,
                    "topic_name": topic_name,
                    "written": False,
                    "collected_points": []
                })
        
        # Embed the topic names for efficient matching
        if self.canonical_topics:
            topic_names = [t["topic_name"] for t in self.canonical_topics]
            self.topic_embeddings = self.embedder.get_embeddings(topic_names)

    def _normalize_topic_name(self, name: str) -> str:
        """Normalizes a topic name to create a consistent ID."""
        return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')

    def match_chunk_to_topics(self, chunk_content: str) -> List[Dict[str, Any]]:
        """
        Matches a chunk's content against the canonical topic list.
        Returns a list of matching topic dictionaries.
        """
        if not self.canonical_topics or self.topic_embeddings is None:
            return []

        chunk_embedding = self.embedder.get_embeddings([chunk_content])[0]
        
        # Perform similarity search to find relevant topics
        # This is a simplified approach; a more robust solution might use FAISS or similar
        similarities = self.embedder.get_similarity_scores(chunk_embedding, self.topic_embeddings)
        
        matching_topics = []
        # Define a similarity threshold for matching
        SIMILARITY_THRESHOLD = 0.2 # Further lowered threshold for even more inclusive matching

        for i, topic in enumerate(self.canonical_topics):
            if similarities[i] >= SIMILARITY_THRESHOLD:
                matching_topics.append(topic)
        
        # If no strong match, try to infer a new topic or broaden the search
        # For now, we'll stick to the canonical list.
        
        return matching_topics

    def collect_information_for_topic(self, chunk_content: str, topic_id: str):
        """
        Extracts new facts from the chunk relevant to the topic and appends them
        to the topic's collected_points, ensuring no duplication.
        """
        for topic in self.canonical_topics:
            if topic["topic_id"] == topic_id:
                # Extract facts from the chunk relevant to this specific topic
                new_facts_raw = self.summarizer.extract_new_facts_for_topic(chunk_content, topic["topic_name"], topic["collected_points"])
                
                # Assuming new_facts_raw is a newline-separated string of facts
                new_facts = [fact.strip() for fact in new_facts_raw.split('\n') if fact.strip()]
                
                for fact in new_facts:
                    # Simple duplication check: check if the exact fact (or a very similar one) already exists
                    is_duplicate = False
                    for existing_fact in topic["collected_points"]:
                        # Using fuzzy matching for more robust duplication detection
                        if fuzz.ratio(fact.lower(), existing_fact.lower()) > 90: # 90% similarity
                            is_duplicate = True
                            break
                    
                    if not is_duplicate:
                        topic["collected_points"].append(fact)
                break

    def get_topics_to_rewrite(self) -> List[Dict[str, Any]]:
        """
        Returns the list of canonical topics, ordered logically (e.g., by initial appearance or importance).
        For now, we'll return them in the order they were canonicalized.
        Later, we can implement a more sophisticated sequencing rule.
        """
        # Implement sequencing rule here if needed. For now, return as is.
        return [topic for topic in self.canonical_topics if topic["collected_points"]]

    def mark_topic_as_written(self, topic_id: str):
        """Marks a topic as written to prevent re-writing."""
        for topic in self.canonical_topics:
            if topic["topic_id"] == topic_id:
                topic["written"] = True
                break

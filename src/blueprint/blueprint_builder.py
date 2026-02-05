import logging
import json
import re
import hashlib
import asyncio
from typing import List, Dict, Any, Tuple, Optional
from src.utils.cpu_manager import CPUExecutionManager
from src.core.gemini.client import GeminiClient
from src.core.gemini.prompts.prompts import (
    PROMPT_BUILD_BLUEPRINT, 
    PROMPT_DETECT_CONTRADICTION, 
    PROMPT_DETECT_CONCEPT_DRIFT,
    PROMPT_ANALYZE_CONTENT_DEPTH,
    PROMPT_MAP_CONCEPTS_TO_STRUCTURE
)
from src.core.semantic.models import SourceBlueprint, DerivedBlueprint, BlueprintNode, ExplanationDepth, ExplanationVariant

logger = logging.getLogger(__name__)

class BlueprintBuilder:
    """
    Orchestrates the creation of a canonical, hierarchical Knowledge Blueprint
    from discovered concepts.
    
    STRICT RULE: This module must execute in a single-threaded, synchronous context.
    """
    def __init__(self):
        self.client = GeminiClient()
        self.cpu_manager = CPUExecutionManager()

    def build_source_blueprint(self, discovered_concepts: List[Dict[str, Any]], book_id: str, original_structure: Optional[List[Dict[str, Any]]] = None) -> SourceBlueprint:
        """
        Builds an authoritative, book-faithful SourceBlueprint as a CLOSED-WORLD constructor.
        STRICT RULE: Number of SourceBlueprint topics == number of TOC slots.
        """
        # Runtime Assertion: Ensure not in an async context
        try:
            asyncio.get_running_loop()
            raise RuntimeError("CRITICAL SAFETY VIOLATION: BlueprintBuilder must NOT be called from an asynchronous context.")
        except RuntimeError as e:
            if "no running event loop" not in str(e):
                raise e

        if not original_structure:
            logger.error("Original structure is required for CLOSED-WORLD SourceBlueprint.")
            raise ValueError("Original structure (TOC) is mandatory for SourceBlueprint creation.")

        logger.info(f"Building CLOSED-WORLD SourceBlueprint for book {book_id}...")
        
        # Step 1: Resolve and ID concepts
        resolved_concepts = self._resolve_contradictions(discovered_concepts)
        id_tasks = [(c.get("concept_name", ""), book_id) for c in resolved_concepts]
        concept_ids = self.cpu_manager.run_parallel(lambda x: self._generate_stable_id(*x), id_tasks)
        for concept, cid in zip(resolved_concepts, concept_ids):
            concept["concept_id"] = cid

        # Step 2: Perform bulk mapping of concepts to structure
        # The original_structure defines the ONLY legal slots.
        structure_paths = list(self._flatten_structure(original_structure).values())
        concept_mapping = self._bulk_map_concepts_to_structure(structure_paths, resolved_concepts)

        # Step 3: Map concepts to original structure and analyze depth
        # This enforces that concepts MUST fit into existing slots.
        hierarchy = self._analyze_and_map_structure(original_structure, resolved_concepts, concept_mapping=concept_mapping)
        
        # Step 4: Identify mapped vs unmapped concepts
        mapped_concept_ids = set()
        def collect_mapped_ids(nodes):
            for n in nodes:
                mapped_concept_ids.update(n.concept_ids)
                if n.children:
                    collect_mapped_ids(n.children)
        collect_mapped_ids(hierarchy)

        # Filter pool to ONLY include mapped concepts (Topics)
        # Unmapped concepts will be handled by the pipeline as metadata
        final_topics = [c for c in resolved_concepts if c["concept_id"] in mapped_concept_ids]
        unmapped_concepts = [c for c in resolved_concepts if c["concept_id"] not in mapped_concept_ids]
        
        # Store unmapped concepts in a temporary attribute for the pipeline to pick up
        self._last_unmapped_concepts = unmapped_concepts

        # ASSERT: Number of SourceBlueprint topics == number of TOC slots
        def count_slots(nodes):
            count = 0
            for n in nodes:
                count += 1
                if n.children:
                    count += count_slots(n.children)
            return count
        
        num_slots = count_slots(hierarchy)
        num_toc_nodes = len(structure_paths)
        logger.info(f"CLOSED-WORLD ASSERTION: {num_slots} slots created from {num_toc_nodes} TOC nodes.")
        
        # RUNTIME ASSERTION: Topic creation happens ONLY in SourceBlueprintBuilder
        # and must exactly match TOC slots.
        if num_slots != num_toc_nodes:
            error_msg = f"CRITICAL ARCHITECTURAL VIOLATION: SourceBlueprint slot count ({num_slots}) does not match TOC node count ({num_toc_nodes})."
            logger.error(error_msg)
            raise AssertionError(error_msg)
        
        source_blueprint = SourceBlueprint(
            book_id=book_id,
            hierarchy=hierarchy,
            concepts=final_topics
        )
        
        logger.info(f"SourceBlueprint successfully built. {len(final_topics)} concepts promoted to topics, {len(unmapped_concepts)} demoted to references.")
        return source_blueprint

    def _bulk_map_concepts_to_structure(self, structure_paths: List[str], concepts: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """
        Uses LLM to map all discovered concepts to the original structure paths in bulk.
        """
        logger.info(f"Performing bulk mapping of {len(concepts)} concepts to {len(structure_paths)} structure nodes...")
        
        concepts_summary = "\n".join([f"- {c['concept_name']} (ID: {c['concept_id']})" for c in concepts])
        structure_paths_str = "\n".join([f"- {p}" for p in structure_paths])
        
        prompt = PROMPT_MAP_CONCEPTS_TO_STRUCTURE.format(
            structure_paths=structure_paths_str,
            concepts_summary=concepts_summary
        )
        
        response = self.client.generate_content(
            prompt=prompt,
            generation_config={"temperature": 0.1}
        )
        
        if response:
            try:
                clean_response = re.sub(r'```json\s*|\s*```', '', response).strip()
                start_idx = clean_response.find('{')
                end_idx = clean_response.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    clean_response = clean_response[start_idx:end_idx+1]
                
                raw_mapping = json.loads(clean_response)
                
                # Robustly map Gemini's response back to stable IDs
                name_to_id = {c["concept_name"].lower().strip(): c["concept_id"] for c in concepts}
                for c in concepts:
                    for alias in c.get("aliases", []):
                        name_to_id[alias.lower().strip()] = c["concept_id"]
                
                id_set = {c["concept_id"] for c in concepts}
                
                final_mapping = {}
                for path, items in raw_mapping.items():
                    resolved_ids = []
                    if isinstance(items, list):
                        for item in items:
                            item_str = str(item).strip()
                            if item_str in id_set:
                                resolved_ids.append(item_str)
                            elif item_str.lower() in name_to_id:
                                resolved_ids.append(name_to_id[item_str.lower()])
                    if resolved_ids:
                        final_mapping[path] = list(dict.fromkeys(resolved_ids))
                
                logger.info(f"Bulk mapping successful. Mapped {len(final_mapping)} nodes.")
                return final_mapping
            except Exception as e:
                logger.error(f"Failed to parse bulk concept mapping: {e}")
                logger.error(f"Raw response: {response}")
        
        return {}

    def _analyze_and_map_structure(self, structure: List[Dict[str, Any]], concepts: List[Dict[str, Any]], parent_path: str = "", concept_mapping: Dict[str, List[str]] = None) -> List[BlueprintNode]:
        """
        Recursively analyzes each node in the original structure.
        Determines usage_type and explanation_depth based on available concepts.
        STRICT RULE: Attach ONLY concepts that are EXPLAINED_CONCEPT and have explicit evidence.
        """
        nodes = []
        concept_mapping = concept_mapping or {}
        
        # Map concepts by ID for easy lookup
        concept_by_id = {c["concept_id"]: c for c in concepts}

        for item in structure:
            title = item["title"]
            current_path = f"{parent_path} > {title}" if parent_path else title
            
            # Get mapped concept IDs for this path
            raw_mapped_cids = concept_mapping.get(current_path, [])
            
            # Fallback: check if title matches any concept name exactly
            if not raw_mapped_cids:
                for c in concepts:
                    if c["concept_name"].lower() == title.lower() or title.lower() in [a.lower() for a in c.get("aliases", [])]:
                        raw_mapped_cids = [c["concept_id"]]
                        break
            
            # FILTER: Attach ONLY concepts that are EXPLAINED_CONCEPT and have explicit evidence
            valid_mapped_cids = []
            for cid in raw_mapped_cids:
                concept = concept_by_id.get(cid)
                if concept and concept.get("classification") == "EXPLAINED_CONCEPT" and concept.get("explanation_evidence"):
                    valid_mapped_cids.append(cid)
                else:
                    logger.debug(f"REJECTING concept '{cid}' for slot '{current_path}' - not explained or missing evidence.")

            usage_type = "referenced_only"
            depth = ExplanationDepth()
            max_extents = []
            
            if valid_mapped_cids:
                logger.debug(f"Node '{current_path}' mapped to valid concepts: {valid_mapped_cids}")
                # Analyze depth for the primary concept (or aggregate)
                primary_concept = concept_by_id.get(valid_mapped_cids[0])
                if primary_concept:
                    usage_type, depth, max_extent = self._analyze_content_depth(primary_concept, current_path)
                    if max_extent:
                        max_extents.append(max_extent)
                
                if len(valid_mapped_cids) > 1:
                    usage_type = "explained"
            else:
                logger.debug(f"Node '{current_path}' has no valid mapped concepts.")
            
            node = BlueprintNode(
                title=title,
                level=1 if not parent_path else (2 if parent_path.count(">") == 0 else 3),
                original_structure_path=current_path,
                usage_type=usage_type,
                explanation_depth=depth,
                max_source_extent="; ".join(max_extents) if max_extents else None,
                concept_ids=valid_mapped_cids
            )

            if "children" in item and item["children"]:
                node.children = self._analyze_and_map_structure(item["children"], concepts, current_path, concept_mapping=concept_mapping)
            
            nodes.append(node)
            
        return nodes

    def _analyze_content_depth(self, concept: Dict[str, Any], node_path: str) -> Tuple[str, ExplanationDepth, Optional[str]]:
        """
        Analyzes the content of a concept using LLM to determine its usage type, explanation depth, and source extent.
        """
        content = concept.get("description", "")
        if not content:
            return "referenced_only", ExplanationDepth(), None

        prompt = PROMPT_ANALYZE_CONTENT_DEPTH.format(
            node_path=node_path,
            content=content
        )

        response = self.client.generate_content(
            prompt=prompt,
            generation_config={"temperature": 0.1}
        )

        if response:
            logger.debug(f"Raw LLM response for content depth analysis: {response}") # Added debug log
            try:
                # Clean response if it contains markdown fences
                clean_response = re.sub(r'```json\s*|\s*```', '', response).strip()
                
                # Robust JSON parsing
                start_idx = clean_response.find('{')
                end_idx = clean_response.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    clean_response = clean_response[start_idx:end_idx+1]
                
                result = json.loads(clean_response)
                
                # Parse new explanation_depth_type and explanation_components
                usage_type = result.get("usage_type", "explained")
                explanation_depth_type = result.get("explanation_depth_type", "intermediate")
                explanation_components = result.get("explanation_components", {})

                depth = ExplanationDepth(
                    definition=explanation_components.get("definition", False),
                    intuition=explanation_components.get("intuition", False),
                    derivation=explanation_components.get("derivation", False),
                    proof=explanation_components.get("proof", False),
                    # Set allowed_expansion based on inferred depth type
                    allowed_expansion="enhance" if explanation_depth_type == "detailed" else "rephrase_only"
                )
                return usage_type, depth, None # max_source_extent is no longer used for importance
            except Exception as e:
                logger.error(f"Failed to parse content depth analysis: {e}")

        # Fallback to basic heuristic if LLM fails
        return "explained", ExplanationDepth(definition=True, intuition=False, derivation=False, proof=False), None

    def build_derived_blueprint(self, source_blueprint: SourceBlueprint, authorial_intent: Optional[str] = None) -> DerivedBlueprint:
        """
        Generates a DerivedBlueprint ONLY from a SourceBlueprint.
        STRICT RULE: Never reads raw PDF text.
        STRICT RULE: Every DerivedBlueprint node MUST map to ≥1 SourceBlueprint topic_id.
        """
        from src.core.gemini.prompts.prompts import PROMPT_GENERATE_DERIVED_BLUEPRINT
        logger.info(f"Generating DerivedBlueprint from SourceBlueprint for book {source_blueprint.book_id}...")
        
        # Prepare source hierarchy for the prompt
        def serialize_node(node: BlueprintNode) -> Dict[str, Any]:
            data = {
                "title": node.title,
                "usage_type": node.usage_type,
                "concept_ids": node.concept_ids,
                "explanation_depth": node.explanation_depth.dict() # Include depth for LLM context
            }
            if node.children:
                data["children"] = [serialize_node(c) for c in node.children]
            return data

        source_hierarchy_json = json.dumps([serialize_node(n) for n in source_blueprint.hierarchy], indent=2)
        
        prompt = PROMPT_GENERATE_DERIVED_BLUEPRINT.format(
            source_hierarchy=source_hierarchy_json,
            authorial_intent=authorial_intent or "Optimize for clarity and exam preparation."
        )

        response = self.client.generate_content(
            prompt=prompt,
            generation_config={"temperature": 0.2}
        )

        if not response:
            logger.error("Failed to generate DerivedBlueprint from LLM.")
            return self._create_fallback_derived_blueprint(source_blueprint, authorial_intent)

        try:
            clean_response = re.sub(r'```json\s*|\s*```', '', response).strip()
            start_idx = clean_response.find('[')
            end_idx = clean_response.rfind(']')
            if start_idx != -1 and end_idx != -1:
                clean_response = clean_response[start_idx:end_idx+1]
            
            derived_hierarchy_raw = json.loads(clean_response)
            
            # Map raw JSON back to BlueprintNode objects and hydrate from source
            source_nodes_by_id = {}
            source_topic_ids = {c["concept_id"] for c in source_blueprint.concepts}
            
            # Also map concepts by ID to get their explanation variants
            source_concepts_by_id = {c["concept_id"]: c for c in source_blueprint.concepts}

            def count_slots(nodes):
                count = 0
                for n in nodes:
                    count += 1
                    if n.children:
                        count += count_slots(n.children)
                return count

            def index_source(nodes):
                for n in nodes:
                    for cid in n.concept_ids:
                        source_nodes_by_id[cid] = n
                    if n.children:
                        index_source(n.children)
            index_source(source_blueprint.hierarchy)

            def map_raw_to_node(raw: Dict[str, Any], level: int) -> Optional[BlueprintNode]:
                title = raw.get("title", "Unknown")
                cids = raw.get("concept_ids", [])
                
                # ENFORCE MAPPING INTEGRITY: Every node MUST map to ≥1 SourceBlueprint topic_id
                valid_cids = [cid for cid in cids if cid in source_topic_ids]
                if not valid_cids and level > 1: # Chapters (level 1) might be containers
                    logger.warning(f"REJECTING DerivedBlueprint node with no valid SourceBlueprint mapping: '{title}' (Level: {level})")
                    return None

                # ENFORCE DEPTH: Cannot increase hierarchy depth
                if level > 3:
                    logger.warning(f"REJECTING DerivedBlueprint node exceeding depth limit: '{title}'")
                    return None
                
                # Aggregate explanation depth and variants from source concepts
                aggregated_depth = ExplanationDepth()
                aggregated_variants = []
                
                for cid in valid_cids:
                    src_concept = source_concepts_by_id.get(cid)
                    src_node = source_nodes_by_id.get(cid) # Define src_node here
                    if src_concept and src_node: # Ensure src_node is available
                        # Aggregate explanation depth components
                        src_depth = src_node.explanation_depth
                        if src_depth:
                            aggregated_depth.definition = aggregated_depth.definition or src_depth.definition
                            aggregated_depth.intuition = aggregated_depth.intuition or src_depth.intuition
                            aggregated_depth.derivation = aggregated_depth.derivation or src_depth.derivation
                            aggregated_depth.proof = aggregated_depth.proof or src_depth.proof
                            
                        # Aggregate explanation variants
                        if "explanation_variants" in src_concept and src_concept["explanation_variants"]:
                            for variant in src_concept["explanation_variants"]:
                                aggregated_variants.append(ExplanationVariant(**variant).dict())
                
                # Determine usage_type for the derived node
                # If any mapped source concept was 'explained', then this derived node is 'explained'
                derived_usage_type = "referenced_only"
                for cid in valid_cids:
                    src_node = source_nodes_by_id.get(cid)
                    if src_node and src_node.usage_type == "explained":
                        derived_usage_type = "explained"
                        break
                    elif src_node and src_node.usage_type == "contextual":
                        derived_usage_type = "contextual" # If no explained, but some contextual

                derived_id = hashlib.sha256(f"{title}_{level}_{'_'.join(cids)}".encode()).hexdigest()[:12]

                node = BlueprintNode(
                    title=title,
                    level=level,
                    derived_topic_id=derived_id,
                    concept_ids=cids,
                    usage_type=derived_usage_type,
                    explanation_depth=aggregated_depth,
                    allowed_expansion=raw.get("allowed_expansion", "rephrase_only"),
                    # max_source_extent is no longer directly used for importance, can be omitted or derived differently
                    # For now, we'll keep it None as it's not directly passed from _analyze_content_depth anymore
                    max_source_extent=None 
                )
                
                # Log merges/renames
                if raw.get("original_title") and raw["original_title"] != title:
                    logger.info(f"DerivedBlueprint: Renamed '{raw['original_title']}' to '{title}'.")
                if len(cids) > 1:
                    logger.info(f"DerivedBlueprint: Merged concepts {cids} into node '{title}'.")

                if "children" in raw:
                    children = []
                    for c in raw["children"]:
                        child_node = map_raw_to_node(c, level + 1)
                        if child_node:
                            children.append(child_node)
                    node.children = children
                return node

            derived_hierarchy = []
            for n in derived_hierarchy_raw:
                node = map_raw_to_node(n, 1)
                if node:
                    derived_hierarchy.append(node)

            # RUNTIME ASSERTION: DerivedBlueprintBuilder never creates new nodes
            def count_derived_slots(nodes):
                count = 0
                for n in nodes:
                    count += 1
                    if n.children:
                        count += count_derived_slots(n.children)
                return count
            
            num_derived_slots = count_derived_slots(derived_hierarchy)
            
            # Use the helper method defined in the class scope
            def count_source_slots(nodes):
                count = 0
                for n in nodes:
                    count += 1
                    if n.children:
                        count += count_source_slots(n.children)
                return count
                
            num_source_slots = count_source_slots(source_blueprint.hierarchy)
            
            if num_derived_slots > num_source_slots:
                error_msg = f"CRITICAL ARCHITECTURAL VIOLATION: DerivedBlueprint attempted to create new nodes ({num_derived_slots} > {num_source_slots})."
                logger.error(error_msg)
                raise AssertionError(error_msg)

            derived = DerivedBlueprint(
                source_blueprint_id=source_blueprint.book_id,
                book_id=source_blueprint.book_id,
                hierarchy=derived_hierarchy,
                concepts=source_blueprint.concepts, # Keep original concepts for now, will refine
                authorial_intent=authorial_intent
            )
            
            logger.info("DerivedBlueprint successfully generated and validated against CLOSED SET.")
            return derived
        except Exception as e:
            logger.error(f"Failed to parse DerivedBlueprint: {e}")
            return self._create_fallback_derived_blueprint(source_blueprint, authorial_intent)

    def _create_fallback_derived_blueprint(self, source_blueprint: SourceBlueprint, authorial_intent: Optional[str] = None) -> DerivedBlueprint:
        """Creates a direct copy of the SourceBlueprint as a fallback DerivedBlueprint."""
        logger.warning("Creating fallback DerivedBlueprint (direct copy of Source).")
        return DerivedBlueprint(
            source_blueprint_id=source_blueprint.book_id,
            book_id=source_blueprint.book_id,
            hierarchy=source_blueprint.hierarchy,
            concepts=source_blueprint.concepts,
            authorial_intent=authorial_intent
        )

    def _map_to_hierarchy(self, raw_blueprint: Dict[str, Any], original_structure: Optional[List[Dict[str, Any]]] = None) -> List[BlueprintNode]:
        """Maps raw LLM JSON structure to BlueprintNode hierarchy and attaches structural anchors."""
        hierarchy = []
        flat_original = self._flatten_structure(original_structure) if original_structure else {}

        for ch in raw_blueprint.get("chapters", []):
            ch_title = ch["title"]
            ch_path = flat_original.get(ch_title.lower(), ch_title)
            
            chapter_node = BlueprintNode(
                title=ch_title, 
                level=1,
                original_structure_path=ch_path
            )
            
            for sec in ch.get("sections", []):
                sec_title = sec["title"]
                sec_path = flat_original.get(sec_title.lower(), f"{ch_path} > {sec_title}")
                
                section_node = BlueprintNode(
                    title=sec_title, 
                    level=2, 
                    original_structure_path=sec_path,
                    concept_ids=sec.get("concept_ids", [])
                )
                chapter_node.children.append(section_node)
            hierarchy.append(chapter_node)
        return hierarchy

    def _flatten_structure(self, structure: List[Dict[str, Any]], parent_path: str = "") -> Dict[str, str]:
        """Flattens hierarchical structure into a title -> path mapping."""
        flat = {}
        for node in structure:
            title = node.get("title", "")
            current_path = f"{parent_path} > {title}" if parent_path else title
            flat[title.lower()] = current_path
            if "children" in node and node["children"]:
                flat.update(self._flatten_structure(node["children"], current_path))
        return flat

    def _count_slots(self, nodes: List[Any]) -> int:
        """Helper to count total nodes in a hierarchy."""
        count = 0
        for n in nodes:
            count += 1
            # Handle both dicts and BlueprintNode objects
            children = []
            if hasattr(n, 'children'):
                children = n.children
            elif isinstance(n, dict):
                children = n.get('children', []) or n.get('sections', [])
            
            if children:
                count += self._count_slots(children)
        return count

    def _create_fallback_source_blueprint(self, concepts: List[Dict[str, Any]], book_id: str) -> SourceBlueprint:
        """Creates a basic flat SourceBlueprint if the LLM fails."""
        fallback_node = BlueprintNode(
            title="General Concepts",
            level=1,
            original_structure_path="General Concepts",
            children=[BlueprintNode(title="All Concepts", level=2, original_structure_path="General Concepts > All Concepts", concept_ids=[c['concept_id'] for c in concepts])]
        )
        return SourceBlueprint(
            book_id=book_id,
            hierarchy=[fallback_node],
            concepts=concepts
        )

    def _hydrate_blueprint(self, blueprint: Dict[str, Any], resolved_concepts: List[Dict[str, Any]]):
        """
        Re-attaches full concept details to the blueprint structure.
        """
        blueprint['concepts'] = resolved_concepts

    def _create_fallback_blueprint(self, concepts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Creates a basic flat blueprint if the LLM fails to generate a complex one.
        """
        logger.warning("Creating fallback flat blueprint.")
        return {
            "chapters": [{"title": "General Concepts", "sections": [{"title": "All Concepts", "concept_ids": [c['concept_id'] for c in concepts]}]}],
            "concepts": concepts,
            "global_confidence": 0.5,
            "render_confidence": 0.5
        }

    def _propagate_confidence(self, blueprint: Dict[str, Any]):
        """
        Calculates weighted confidence scores across the hierarchy.
        Hierarchy: Chapter -> Section -> Concept
        Weights: core=1.0, supporting=0.6, optional=0.3
        """
        importance_weights = {"core": 1.0, "supporting": 0.6, "optional": 0.3}
        
        concepts_list = blueprint.get('concepts', [])
        concepts_map = {c.get('concept_id') or c.get('concept_name'): c for c in concepts_list}
        
        total_weighted_confidence = 0.0
        total_weight = 0.0

        for chapter in blueprint.get('chapters', []):
            chapter_weighted_conf = 0.0
            chapter_total_weight = 0.0
            
            for section in chapter.get('sections', []):
                section_concept_ids = section.get('concept_ids', [])
                
                section_weighted_conf = 0.0
                section_total_weight = 0.0
                
                for cid in section_concept_ids:
                    concept = concepts_map.get(cid)
                    if concept:
                        importance = concept.get('importance', 'supporting')
                        weight = importance_weights.get(importance, 0.5)
                        confidence = concept.get('confidence', 0.0)
                        
                        section_weighted_conf += (confidence * weight)
                        section_total_weight += weight
                        
                        chapter_weighted_conf += (confidence * weight)
                        chapter_total_weight += weight
                        
                        total_weighted_confidence += (confidence * weight)
                        total_weight += weight
                
                if section_total_weight > 0:
                    section['confidence'] = round(section_weighted_conf / section_total_weight, 2)
                else:
                    section['confidence'] = 0.0
            
            if chapter_total_weight > 0:
                chapter['confidence'] = round(chapter_weighted_conf / chapter_total_weight, 2)
            else:
                chapter['confidence'] = 0.0

        if total_weight > 0:
            blueprint['render_confidence'] = round(total_weighted_confidence / total_weight, 2)
        else:
            blueprint['render_confidence'] = 0.0
            
        logger.info(f"Blueprint Render Confidence: {blueprint['render_confidence']}")

    def _generate_stable_id(self, concept_name: str, book_id: str) -> str:
        """
        Generates a stable, unique identifier for a concept within a book.
        """
        normalized_name = concept_name.lower().strip().replace(" ", "_")
        raw_id = f"{normalized_name}_{book_id}"
        return hashlib.sha256(raw_id.encode()).hexdigest()[:16]

    def _resolve_contradictions(self, concepts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Detects and resolves factual contradictions between similar concepts (Synchronous).
        """
        if len(concepts) < 2:
            return concepts

        logger.info("Starting contradiction detection and explanation aggregation phase...")
        
        # Group concepts by normalized term for initial comparison
        concept_groups: Dict[str, List[Dict[str, Any]]] = {}
        for c in concepts:
            name = c.get("concept_name", "unknown").lower().strip()
            if name not in concept_groups:
                concept_groups[name] = []
            concept_groups[name].append(c)

        final_concepts_with_variants = []
        for name, group in concept_groups.items():
            if not group:
                continue

            # The first concept in the group (sorted by confidence) becomes the canonical concept
            # All its explanations will be stored as variants.
            canonical_concept = group[0]
            
            # Initialize explanation variants list for the canonical concept
            if "explanation_variants" not in canonical_concept:
                canonical_concept["explanation_variants"] = []

            # Add the primary explanation as a variant
            if canonical_concept.get("verbatim_evidence"):
                canonical_concept["explanation_variants"].append(ExplanationVariant(
                    text=canonical_concept["verbatim_evidence"],
                    depth_type="detailed", # Heuristic for now, will be refined by _analyze_content_depth
                    usage_type="core",
                    source_chapter_or_chunk_range=f"Chunk {canonical_concept.get('source_chunk_index')}",
                    original_concept_id=canonical_concept.get("concept_id"),
                    confidence=canonical_concept.get("confidence", 0.0)
                ).dict())
            
            # Process remaining concepts in the group for contradictions or aggregation
            for i in range(1, len(group)):
                secondary_concept = group[i]
                
                # Perform TRUE CONTRADICTION DETECTION
                prompt = PROMPT_DETECT_CONTRADICTION.format(
                    text1=canonical_concept.get("verbatim_evidence", ""),
                    text2=secondary_concept.get("verbatim_evidence", "")
                )
                
                response = self.client.generate_content(prompt, generation_config={"temperature": 0.1})
                if response:
                    try:
                        clean_response = re.sub(r'```json\s*|\s*```', '', response).strip()
                        result = json.loads(clean_response)
                        
                        if result.get("conflict"):
                            logger.warning(f"TRUE CONTRADICTION DETECTED for '{name}': {result.get('reason')}")
                            # Mark the canonical concept with conflict metadata
                            if "metadata" not in canonical_concept: canonical_concept["metadata"] = {}
                            canonical_concept["metadata"]["conflict"] = True
                            canonical_concept["metadata"]["contradiction_report"] = {
                                "conflicting_concept_name": secondary_concept.get("concept_name"),
                                "reason": result.get("reason"),
                                "conflicting_evidence_preview": secondary_concept.get("verbatim_evidence", "")[:100] + "...",
                                "resolution_strategy": "flagged_for_manual_review" # No automatic resolution for true conflicts
                            }
                            # Do NOT add conflicting explanation as a variant
                            logger.info(f"Logged true contradiction for '{name}'. Conflicting explanation from chunk {secondary_concept.get('source_chunk_index')} was NOT aggregated.")
                        else:
                            # If no true conflict, aggregate the explanation as a variant
                            logger.info(f"No true semantic contradiction for '{name}'. Aggregating explanation from chunk {secondary_concept.get('source_chunk_index')} as a variant.")
                            if secondary_concept.get("verbatim_evidence"):
                                canonical_concept["explanation_variants"].append(ExplanationVariant(
                                    text=secondary_concept["verbatim_evidence"],
                                    depth_type="intermediate", # Heuristic for now
                                    usage_type="contextual", # Heuristic for now
                                    source_chapter_or_chunk_range=f"Chunk {secondary_concept.get('source_chunk_index')}",
                                    original_concept_id=secondary_concept.get("concept_id"),
                                    confidence=secondary_concept.get("confidence", 0.0)
                                ).dict())
                                logger.info(f"Explanation from chunk {secondary_concept.get('source_chunk_index')} aggregated as variant for '{name}'.")
                            
                            if "metadata" not in canonical_concept: canonical_concept["metadata"] = {}
                            canonical_concept["metadata"]["aggregated_from"] = canonical_concept["metadata"].get("aggregated_from", []) + [{
                                "concept_name": secondary_concept.get("concept_name"),
                                "source_chunk": secondary_concept.get("source_chunk_index"),
                                "explanation_aggregated": True,
                                "examples_merged": False # Examples are no longer merged
                            }]
                            logger.info(f"Examples from chunk {secondary_concept.get('source_chunk_index')} were NOT merged for '{name}'.")

                    except Exception as e:
                        logger.error(f"Contradiction detection or aggregation failed for '{name}': {e}")
                        logger.debug(f"Raw LLM response: {response}")
            
            final_concepts_with_variants.append(canonical_concept)

        return final_concepts_with_variants

    def _detect_concept_drift(self, resolved_concepts: List[Dict[str, Any]], all_raw_concepts: List[Dict[str, Any]]):
        """
        Detects if a concept's meaning or emphasis drifts across distant parts of the book (Synchronous).
        """
        logger.info("Starting concept drift detection...")
        
        occurrences: Dict[str, List[Dict[str, Any]]] = {}
        for c in all_raw_concepts:
            name = c.get("concept_name", "unknown").lower().strip()
            if name not in occurrences:
                occurrences[name] = []
            occurrences[name].append(c)

        for concept in resolved_concepts:
            name = concept.get("concept_name", "unknown").lower().strip()
            concept_occurrences = occurrences.get(name, [])
            
            if len(concept_occurrences) < 2:
                continue

            sorted_occ = sorted(concept_occurrences, key=lambda x: x.get("source_chunk_index", 0))
            first = sorted_occ[0]
            last = sorted_occ[-1]
            
            distance = last.get("source_chunk_index", 0) - first.get("source_chunk_index", 0)
            
            if distance >= 5:
                logger.info(f"Checking drift for '{name}' (Distance: {distance} chunks)")
                
                prompt = PROMPT_DETECT_CONCEPT_DRIFT.format(
                    early_text=first.get("description", ""),
                    late_text=last.get("description", "")
                )
                
                response = self.client.generate_content(prompt, generation_config={"temperature": 0.1})
                if response:
                    try:
                        clean_response = re.sub(r'```json\s*|\s*```', '', response).strip()
                        result = json.loads(clean_response)
                        
                        if result.get("drift_warning"):
                            logger.warning(f"CONCEPT DRIFT DETECTED for '{name}': {result.get('reason')}")
                            concept["drift_warning"] = True
                            concept["drift_reason"] = result.get("reason")
                    except Exception as e:
                        logger.error(f"Drift detection parsing failed: {e}")

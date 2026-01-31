import os
import time
import logging
import re
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Set

from src.config import PDF_FOLDER, OUTPUT_FOLDER, CHUNK_SIZE_WORDS, ACTIVE_MODEL
from src.utils.pdf_reader import PDFReader
from src.export.word_exporter import WordExporter
from src.storage.knowledge_store import KnowledgeStore
from src.storage.book_repository import BookRepository
from src.storage.topic_repository import TopicRepository
from src.storage.schema import BookMetadata, TopicKnowledge
from src.utils.execution_trace import ExecutionTrace

logger = logging.getLogger(__name__)

if ACTIVE_MODEL == "GEMINI":
    from src.core.gemini.chunker import Chunker
    from src.core.gemini.summarizer import Summarizer as GeminiSummarizer
    from src.structure.structure_extractor import StructureExtractor as GeminiStructureExtractor
    from src.core.gemini.content_mapper import ContentMapper as GeminiContentMapper
    from src.core.gemini.concept_consolidator import ConceptConsolidator as GeminiConceptConsolidator
    from src.render.academic_note_writer import AcademicNoteWriter as GeminiAcademicNoteWriter
    from src.discovery.concept_discovery import ConceptDiscoveryAgent
    from src.blueprint.blueprint_builder import BlueprintBuilder
    from src.core.gemini.renderer_profiles import PROFILES
    from src.verify.verifier import VerifierAgent
else:
    # Fallbacks or other models could be imported here
    pass

class SmartBookRewriterEnhanced:
    """
    A comprehensive pipeline for rewriting PDF book content into structured,
    exam-oriented notes.
    """

    def __init__(self, pdf_folder: str = PDF_FOLDER, output_folder: str = OUTPUT_FOLDER):
        self.pdf_folder = pdf_folder
        self.output_folder = output_folder
        os.makedirs(self.output_folder, exist_ok=True)
        self.book_title = "Rewritten Book Notes"
        self.current_book_id = None
        self.structured_book = None # Cache for ingested structure and content

        self.pdf_reader = PDFReader(pdf_folder=self.pdf_folder)
        self.chunker = Chunker(chunk_size_words=CHUNK_SIZE_WORDS)
        
        if ACTIVE_MODEL == "GEMINI":
            self.summarizer = GeminiSummarizer()
            self.structure_extractor = GeminiStructureExtractor()
            self.content_mapper = GeminiContentMapper()
            self.concept_consolidator = GeminiConceptConsolidator()
            self.academic_writer = GeminiAcademicNoteWriter()
            self.concept_discovery = ConceptDiscoveryAgent()
            self.blueprint_builder = BlueprintBuilder()
            self.verifier = VerifierAgent()
        else:
            raise ValueError(f"Unsupported ACTIVE_MODEL: {ACTIVE_MODEL}")
            
        self.word_exporter = WordExporter(output_folder=self.output_folder)
        
        # Storage Layer
        self.store = KnowledgeStore()
        self.book_repo = BookRepository(self.store)
        self.topic_repo = TopicRepository(self.store)
        self.trace = ExecutionTrace()
        
        # Update agents to use the shared trace
        self.concept_discovery.async_manager.trace = self.trace
        self.academic_writer.async_manager.trace = self.trace

    def _calculate_book_hash(self, pages_data: List[Dict[str, Any]]) -> str:
        """Calculates a stable hash of the PDF content."""
        full_text = "".join([p["text"] for p in pages_data])
        return hashlib.sha256(full_text.encode()).hexdigest()

    def ingest(self, specific_file: str = None):
        """
        Ingests PDFs using semantic chunking, concept discovery, and blueprint building.
        Removes dependency on TOC/Structure extraction.
        """
        logger.info("Starting semantic ingestion process...")
        try:
            pages_data, self.book_title = self.pdf_reader.read_all_pdfs(specific_file=specific_file)
        except Exception as e:
            logger.error(f"Ingestion failed at PDF reading stage: {e}")
            return

        # Save Book Metadata
        book_meta = BookMetadata(
            title=self.book_title,
            source_file_name=self.book_title,
            total_pages=len(pages_data)
        )
        self.book_repo.save_book(book_meta)
        self.current_book_id = book_meta.book_id

        full_text = "\n\n".join([p["text"] for p in pages_data])
        
        # Phase 1: Semantic Chunking & Noise Removal
        logger.info("Phase 1: Performing semantic chunking and noise removal...")
        semantic_chunks = self.chunker.semantic_chunking(full_text, trace=self.trace)
        
        if not semantic_chunks:
            self.trace.log_stage("Chunker", "semantic_chunking", 0.0, "failed")
            logger.error("No semantic chunks extracted.")
            return
        self.trace.log_stage("Chunker", "semantic_chunking", 1.0, "passed")

        # Phase 2: Concept Discovery (Parallel Execution with Trace)
        logger.info(f"Phase 2: Discovering concepts from {len(semantic_chunks)} semantic chunks in parallel...")
        
        # Provide task names for better tracing
        task_names = [f"discovery_chunk_{i}" for i in range(len(semantic_chunks))]
        # Pass task definitions (func, args, kwargs) instead of coroutines
        task_defs = [
            (self.concept_discovery.discover_concepts_async, (chunk, self.trace, f"discovery_chunk_{i}"), {}) 
            for i, chunk in enumerate(semantic_chunks)
        ]
        batch_results = self.concept_discovery.async_manager.run_parallel(
            task_defs,
            task_names=task_names
        )
        
        all_discovered_concepts = []
        all_metadata_terms = []
        for i, result in enumerate(batch_results):
            if result: # result is a List[ConceptTermRecord]
                for record in result:
                    term_dict = record.dict()
                    term_dict["source_chunk_index"] = i
                    
                    if record.classification == "EXPLAINED_CONCEPT":
                        # Map to old schema for blueprint builder compatibility
                        # TODO: Update BlueprintBuilder to use ConceptTermRecord directly
                        legacy_concept = {
                            "concept_name": record.term,
                            "explanation_evidence": record.verbatim_evidence,
                            "description": record.verbatim_evidence, # Use evidence as description for now
                            "classification": record.classification,
                            "source_chunk_index": i,
                            "confidence": record.confidence,
                            "importance": "supporting", # Default
                            "aliases": []
                        }
                        all_discovered_concepts.append(legacy_concept)
                    else:
                        all_metadata_terms.append({
                            "concept_name": record.term,
                            "classification": record.classification,
                            "source_chunk_index": i
                        })

        # Phase 3: Dual-Blueprint Building
        logger.info("Phase 3: Building Dual-Blueprint Architecture...")
        
        # 3.0: Extract Original Structural Anchor (Trusted for Hierarchy Only)
        logger.info("Extracting original book structure as anchor...")
        original_structure = self.structure_extractor.extract_structure(full_text)
        
        if not original_structure:
            logger.error("CRITICAL: Failed to extract book structure. CLOSED SET enforcement requires a valid TOC.")
            self.trace.log_stage("StructureExtractor", "extract_structure", 0.0, "failed")
            return
        self.trace.log_stage("StructureExtractor", "extract_structure", 1.0, "passed")

        # 3.1: Build SourceBlueprint (Authoritative, Book-Faithful)
        source_blueprint = self.blueprint_builder.build_source_blueprint(
            all_discovered_concepts, 
            book_meta.book_id,
            original_structure=original_structure
        )
        
        if not source_blueprint:
            self.trace.log_stage("BlueprintBuilder", "build_source_blueprint", 0.0, "failed")
            logger.error("Failed to build SourceBlueprint.")
            return
        self.trace.log_stage("BlueprintBuilder", "build_source_blueprint", 1.0, "passed")

        # Pick up unmapped concepts from BlueprintBuilder for metadata storage
        unmapped_concepts = getattr(self.blueprint_builder, "_last_unmapped_concepts", [])
        for uc in unmapped_concepts:
            all_metadata_terms.append({
                "concept_name": uc.get("concept_name"),
                "classification": uc.get("classification", "REFERENCED_ONLY"),
                "source_chunk_index": uc.get("source_chunk_index")
            })

        # 3.2: Build DerivedBlueprint (Authorial, User-Facing)
        # STRICT RULE: DerivedBlueprint is generated ONLY from SourceBlueprint.
        derived_blueprint = self.blueprint_builder.build_derived_blueprint(source_blueprint)
        
        if not derived_blueprint:
            self.trace.log_stage("BlueprintBuilder", "build_derived_blueprint", 0.0, "failed")
            logger.error("Failed to build DerivedBlueprint.")
            return
        self.trace.log_stage("BlueprintBuilder", "build_derived_blueprint", 1.0, "passed")

        # Phase 4: Finalized Storage
        logger.info("Phase 4: Storing finalized Knowledge Blueprints...")
        # Store concepts from derived blueprint (which came from source)
        for concept in derived_blueprint.concepts:
            # Determine importance based on TOC position and explicit explanation
            # For now, a simple heuristic: concepts mapped to higher-level TOC nodes are more important
            # This will be refined further in BlueprintBuilder._analyze_content_depth
            importance_score = 0.5 # Default
            if concept.get("classification") == "EXPLAINED_CONCEPT" and concept.get("verbatim_evidence"):
                importance_score = 0.8 # Explicitly explained concepts are more important

            # Aggregate all explanation variants into a single raw_content string for TopicKnowledge
            # This is a temporary measure until TopicKnowledge can store ExplanationVariant objects directly
            all_explanations_text = ""
            if "explanation_variants" in concept and concept["explanation_variants"]:
                for variant in concept["explanation_variants"]:
                    all_explanations_text += f"--- Explanation ({variant.get('depth_type', 'unknown')}, {variant.get('usage_type', 'unknown')}) from {variant.get('source_chapter_or_chunk_range', 'unknown')} ---\n"
                    all_explanations_text += variant.get("text", "") + "\n\n"
            else:
                all_explanations_text = concept.get("verbatim_evidence", "") # Fallback to original if no variants

            topic_knowledge = TopicKnowledge(
                concept_id=concept.get("concept_id"),
                book_id=book_meta.book_id,
                topic=concept.get("concept_name", "Unknown Concept"),
                importance_score=importance_score, # Updated importance logic
                raw_content=all_explanations_text.strip(), # Store aggregated explanations
                topic_type="canonical_concept",
                metadata={
                    "aliases": concept.get("aliases", []),
                    "examples": concept.get("examples", []),
                    "dependencies": concept.get("dependencies", []),
                    "confidence": concept.get("confidence", 0.0),
                    "explanation_evidence": concept.get("verbatim_evidence"), # Keep original evidence for reference
                    "explanation_variants": concept.get("explanation_variants", []) # Store variants in metadata
                }
            )
            self.topic_repo.save_topic(topic_knowledge)

        # Store non-concept terms as metadata in book metadata
        book_meta.metadata["extracted_terms"] = {
            "referenced_only": [t for t in all_metadata_terms if t.get("classification") == "REFERENCED_ONLY"],
            "dependency_only": [t for t in all_metadata_terms if t.get("classification") == "DEPENDENCY_ONLY"]
        }
        
        # Store dual-blueprint metadata
        book_meta.metadata["source_blueprint"] = source_blueprint.dict()
        book_meta.metadata["derived_blueprint"] = derived_blueprint.dict()
        
        # Use SourceBlueprint for the 'blueprint' key to preserve original structure by default
        # We store the full hierarchy as a list of dicts to maintain recursive structure
        book_meta.metadata["blueprint"] = {
            "chapters": [node.dict() for node in source_blueprint.hierarchy],
            "global_confidence": 1.0,
            "render_confidence": 1.0,
            "provenance": {
                "blueprint_version": "2.0",
                "generated_at": datetime.utcnow().isoformat(),
                "book_hash": self._calculate_book_hash(pages_data),
                "pipeline_version": "dual-blueprint-v1"
            }
        }
        self.book_repo.save_book(book_meta)

        logger.info("Ingestion complete. Immutable Knowledge Blueprint finalized.")

    def _store_mapped_page(self, nodes: List[Dict[str, Any]], book_id: str, page_number: int, parent_topic: str = None):
        for node in nodes:
            if 'raw_content' in node and node['raw_content']:
                # Store each piece of content found on this page for this topic
                for content in node['raw_content']:
                    topic_knowledge = TopicKnowledge(
                        book_id=book_id,
                        topic=node['title'],
                        subtopic=parent_topic,
                        source_page=page_number,
                        importance_score=0.8 if parent_topic is None else 0.5, # Simple heuristic
                        raw_content=content,
                        topic_type="core_concept" if parent_topic is None else "sub_concept"
                    )
                    self.topic_repo.save_topic(topic_knowledge)
            
            if 'children' in node and node['children']:
                self._store_mapped_page(node['children'], book_id, page_number, node['title'])

    def run(self, intent: Any = None, export_to_word: bool = True, specific_file: str = None) -> Dict[str, str]:
        """
        Executes the blueprint-based book rewriting pipeline with intent-based routing.
        """
        from src.interaction.command_parser import IntentResult
        self.trace.clear()
        
        if intent is None:
            intent = IntentResult(
                task_type="rewrite_book",
                scope="full_book",
                depth="medium",
                language_level="standard",
                format_type="paragraph",
                allow_external_knowledge=False,
                normalized_query="rewrite book"
            )

        start = time.time()
        
        # Fetch canonical concepts from DB
        logger.info("Fetching canonical concepts from Knowledge Blueprint...")
        if self.current_book_id:
            canonical_concepts = self.topic_repo.get_topics_by_book(self.current_book_id)
        else:
            canonical_concepts = self.topic_repo.get_all_topics()
        
        if not canonical_concepts:
            self.trace.log_stage("Pipeline", "fetch_blueprint", 0.0, "failed")
            return {"error": "No knowledge blueprint found. Please ingest a book first."}
        self.trace.log_stage("Pipeline", "fetch_blueprint", 1.0, "passed")

        # Phase 4: Controlled Rewriting (Blueprint-Aware)
        logger.info("Phase 4: Controlled rewriting using Knowledge Blueprint...")
        
        # Fetch Blueprint Metadata and route based on intent
        render_confidence = 1.0
        blueprint_meta = {}
        reference_only_terms = []
        use_source_blueprint = False

        if intent and intent.refers_to_original_structure:
            logger.info("Routing to SourceBlueprint based on intent (original structure reference).")
            use_source_blueprint = True
        elif intent and intent.task_type == "question_answer":
            logger.info("Routing to SourceBlueprint for Q&A resolution.")
            use_source_blueprint = True

        if self.current_book_id:
            book_meta = self.book_repo.get_book(self.current_book_id)
            if book_meta:
                if use_source_blueprint and "source_blueprint" in book_meta.metadata:
                    # Route to SourceBlueprint
                    source_bp_raw = book_meta.metadata["source_blueprint"]
                    # Flatten for renderer compatibility
                    blueprint_meta = {"chapters": self._flatten_source_for_renderer(source_bp_raw.get("hierarchy", []))}
                    render_confidence = 1.0
                    self.trace.log_blueprint_usage("SourceBlueprint", {"reason": "Intent routing", "structural_restriction": "Strict hierarchy preserved"})
                elif "blueprint" in book_meta.metadata:
                    # Default to DerivedBlueprint (stored in 'blueprint' key for compatibility)
                    blueprint_meta = book_meta.metadata["blueprint"]
                    render_confidence = blueprint_meta.get("render_confidence", 1.0)
                    self.trace.log_blueprint_usage("DerivedBlueprint", {"reason": "Default authorial flow", "structural_restriction": "Merging/Renaming allowed"})
                
                if "extracted_terms" in book_meta.metadata:
                    terms_meta = book_meta.metadata["extracted_terms"]
                    # Combine REFERENCED_ONLY and DEPENDENCY_ONLY for the writer
                    ref_terms = [t.get("concept_name") for t in terms_meta.get("referenced_only", [])]
                    dep_terms = [t.get("concept_name") for t in terms_meta.get("dependency_only", [])]
                    reference_only_terms = list(set(filter(None, ref_terms + dep_terms)))
        
        if not blueprint_meta:
            self.trace.log_blueprint_usage("None/Fallback", {"reason": "No book ID or metadata found", "structural_restriction": "Flat list fallback"})

        # Select Renderer Profile based on task type
        profile = PROFILES["NOTES_MODE"]
        if intent:
            if intent.task_type == "rewrite_book":
                profile = PROFILES["BOOK_MODE"]
            elif intent.task_type == "revision_notes":
                profile = PROFILES["EXAM_NOTES_MODE"]
        
        logger.info(f"Using Renderer Profile: {profile.name} (Global Confidence: {render_confidence})")

        # Map concepts by ID for easy lookup
        concepts_map = {c.concept_id: c for c in canonical_concepts if c.concept_id}
        logger.info(f"Mapped {len(concepts_map)} concepts from database.")
        
        # Prepare tasks based on Blueprint Hierarchy (SLOT-CENTRIC)
        tasks = []
        hierarchy_order = [] # List of (type, title, slot_id, level)
        
        def process_hierarchy_node(node_data, level):
            title = node_data.get("title")
            cids = node_data.get("concept_ids", [])
            usage_type = node_data.get("usage_type", "explained")
            section_depth = node_data.get("explanation_depth")
            section_extent = node_data.get("max_source_extent")
            allowed_expansion = node_data.get("allowed_expansion", "rephrase_only")

            # Unique ID for this slot to map results back
            slot_id = hashlib.sha256(f"{title}_{level}_{json.dumps(cids)}".encode()).hexdigest()[:12]

            # Support up to 4 levels of headings to match original structure
            if level <= 4:
                hierarchy_order.append(("heading", title, slot_id, level))
            else:
                hierarchy_order.append(("sub_heading", title, slot_id, level))
            
            # CONSOLIDATE: Merge all concepts mapped to this slot into one rendering task
            slot_content_parts = []
            slot_examples = []
            slot_dependencies = []
            
            for cid in cids:
                concept = concepts_map.get(cid)
                if concept:
                    slot_content_parts.append(f"--- CONCEPT: {concept.topic} ---\n{concept.raw_content}")
                    metadata = concept.metadata if isinstance(concept.metadata, dict) else {}
                    slot_examples.extend(metadata.get("examples", []))
                    slot_dependencies.extend(metadata.get("dependencies", []))
            
            if slot_content_parts:
                from src.core.semantic.models import ExplanationDepth
                if isinstance(section_depth, dict):
                    section_depth['allowed_expansion'] = allowed_expansion
                    writer_depth = ExplanationDepth(**section_depth)
                else:
                    writer_depth = ExplanationDepth(allowed_expansion=allowed_expansion)

                tasks.append({
                    "topic_name": title,
                    "node_content": "\n\n".join(slot_content_parts),
                    "explanation_depth": writer_depth,
                    "max_source_extent": section_extent,
                    "source_topic_ids": cids,
                    "relationships": [{"topic": d, "relation": "depends_on"} for d in list(set(slot_dependencies))],
                    "already_explained": [], 
                    "tagged_examples": slot_examples, # Pass collected examples
                    "reference_only_terms": reference_only_terms,
                    "profile": profile,
                    "render_confidence": render_confidence,
                    "slot_id": slot_id # Custom field for mapping
                })
            
            # Process children
            children = node_data.get("sections", []) or node_data.get("children", [])
            for child in children:
                process_hierarchy_node(child, level + 1)

        if blueprint_meta and "chapters" in blueprint_meta and blueprint_meta["chapters"]:
            logger.info(f"Processing hierarchy with {len(blueprint_meta['chapters'])} chapters.")
            for chapter in blueprint_meta["chapters"]:
                process_hierarchy_node(chapter, 1)
        else:
            logger.warning("No hierarchy found in blueprint metadata. Falling back to flat list.")
            # Fallback to flat list if no blueprint hierarchy
            for concept in canonical_concepts:
                if concept.topic_type != "canonical_concept":
                    continue
                hierarchy_order.append(("concept", concept.topic, concept.concept_id, 3))
                metadata = concept.metadata if isinstance(concept.metadata, dict) else {}
                tasks.append({
                    "topic_name": concept.topic,
                    "node_content": concept.raw_content,
                    "explanation_depth": intent.depth if intent else "medium",
                    "source_topic_ids": [concept.concept_id] if concept.concept_id else [],
                    "relationships": [{"topic": d, "relation": "depends_on"} for d in metadata.get("dependencies", [])],
                    "already_explained": [],
                    "tagged_examples": metadata.get("examples", []),
                    "reference_only_terms": reference_only_terms,
                    "profile": profile,
                    "render_confidence": render_confidence
                })

        final_notes_parts: List[str] = []
        results_map = {}
        if tasks:
            logger.info(f"Generating notes for {len(tasks)} TOC slots in parallel...")
            batch_results = self.academic_writer.write_notes_batch(tasks, trace=self.trace)
            
            # Map results back to slot IDs for robust lookup
            results_map = {tasks[i]["slot_id"]: batch_results[i] for i in range(len(tasks))}
            
        # Reconstruct final output following hierarchy
        for item_type, title, slot_id, level in hierarchy_order:
            if item_type == "heading":
                final_notes_parts.append(f"{'#' * min(level, 6)} {title}\n\n")
            elif item_type == "sub_heading":
                final_notes_parts.append(f"**{title}**\n\n")
            
            # Append content for this slot if it exists
            result = results_map.get(slot_id)
            if result:
                rewritten = result.get("markdown", "")
                if rewritten.strip():
                    # Aggressively strip ALL headings from LLM output to enforce hierarchy freeze
                    content = re.sub(r'^#+.*?\n', '', rewritten, flags=re.MULTILINE).strip()
                    final_notes_parts.append(f"{content}\n\n")
        
        if not final_notes_parts:
            return {"error": "No final notes generated."}

        final_content = "".join(final_notes_parts).strip()

        # VerifierAgent receives FULL merged output (Synchronous)
        logger.info("Verifying full merged output for structural and content integrity...")
        
        # Prepare rich context for verifier
        def simplify_hierarchy(nodes):
            simple = []
            for n in nodes:
                simple.append({"title": n.get("title"), "level": n.get("level")})
                children = n.get("sections", []) or n.get("children", [])
                if children:
                    simple.extend(simplify_hierarchy(children))
            return simple

        verifier_context = {
            "hierarchy": simplify_hierarchy(blueprint_meta.get("chapters", [])),
            "concepts": [c.topic for c in canonical_concepts],
            "reference_only": reference_only_terms
        }

        verification = self.verifier.verify(
            generated_output=final_content,
            blueprint_context=json.dumps(verifier_context, indent=2, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o)),
            profile=profile
        )

        if not verification.get("valid"):
            logger.warning(f"Output verification failed: {verification.get('reason')}")
            logger.info("Attempting regeneration with reduced content freedom...")
            
            # Reduce content freedom automatically
            from src.core.gemini.renderer_profiles import ContentFreedom
            stricter_profile = profile.copy(update={"content_freedom": ContentFreedom.FORBIDDEN})
            
            # Update tasks with stricter profile
            for task in tasks:
                task["profile"] = stricter_profile
            
            # Regenerate ONCE
            batch_results = self.academic_writer.write_notes_batch(tasks, trace=self.trace)
            results_map = {tasks[i]["source_topic_ids"][0]: batch_results[i] for i in range(len(tasks))}
            
            final_notes_parts = []
            for item_type, title, cid, level in hierarchy_order:
                if item_type == "heading":
                    final_notes_parts.append(f"{'#' * min(level, 6)} {title}\n\n")
                elif item_type == "sub_heading":
                    final_notes_parts.append(f"**{title}**\n\n")
                elif item_type == "concept":
                    result = results_map.get(cid)
                    if result:
                        content = re.sub(r'^#+.*?\n', '', result.get("markdown", ""), flags=re.MULTILINE).strip()
                        final_notes_parts.append(f"{content}\n\n")
            
            final_content = "".join(final_notes_parts).strip()
            
            # Re-verify after regeneration
            verification = self.verifier.verify(
                generated_output=final_content,
                blueprint_context=json.dumps(verifier_context, indent=2, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o)),
                profile=stricter_profile
            )
            
            if not verification.get("valid"):
                error_msg = f"HARD FAILURE: Regeneration failed to resolve invariance violations. Reason: {verification.get('reason')}"
                logger.error(error_msg)
                
                # Log rejected render to trace
                self.trace.log_rejected_render(
                    reason=verification.get("reason", "Unknown"),
                    stats=verification.get("stats", {})
                )
                
                # Log specific violations
                for violation in verification.get("violations", []):
                    self.trace.log_structural_violation(violation, verification.get("stats", {}))

                return {"error": error_msg, "verification_report": verification}
        
        # Generate Confidence Reason
        conf_reasons = []
        if render_confidence > 0.8: conf_reasons.append("High coverage")
        else: conf_reasons.append("Partial coverage")
        
        has_conflicts = any(c.metadata.get("conflict") for c in canonical_concepts if isinstance(c.metadata, dict))
        has_drift = any(c.metadata.get("drift_warning") for c in canonical_concepts if isinstance(c.metadata, dict))
        
        if not has_conflicts: conf_reasons.append("no conflicts")
        else: conf_reasons.append("resolved conflicts")
        
        if not has_drift: conf_reasons.append("low drift")
        else: conf_reasons.append("detected drift")

        # Collect detailed contradiction reports
        contradiction_reports = []
        for c in canonical_concepts:
            if isinstance(c.metadata, dict) and c.metadata.get("conflict"):
                report = {
                    "concept_name": c.topic,
                    "reason": c.metadata.get("rejected_reference", {}).get("reason", "Unknown reason"),
                    "rejected_content_preview": c.metadata.get("rejected_reference", {}).get("description", "")[:100] + "...",
                    "resolution_status": c.metadata.get("resolution_status", "resolved_to_primary")
                }
                contradiction_reports.append(report)

        result = {
            "markdown": final_content,
            "metadata": {
                "render_confidence": render_confidence,
                "confidence_reason": ", ".join(conf_reasons),
                "contradiction_reports": contradiction_reports if contradiction_reports else "No contradictions detected."
            }
        }
        
        if export_to_word:
            book_data = self.word_exporter.assemble_full_book_structured_text([final_content], self.book_title)
            word_path = self.word_exporter.structured_text_to_word(book_data, f"{self.book_title}.docx", toc_depth=2)
            result["docx"] = word_path

        elapsed = time.time() - start
        logger.info(f"Completed in {elapsed/60:.2f} minutes.")
        return result

    def _flatten_source_for_renderer(self, hierarchy: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Converts SourceBlueprint hierarchy to the flat format expected by the renderer."""
        chapters = []
        for node_raw in hierarchy:
            if node_raw.get("level") == 1:
                ch = {
                    "title": node_raw.get("title"),
                    "sections": []
                }
                for child in node_raw.get("children", []):
                    sec = {
                        "title": child.get("title"),
                        "concept_ids": child.get("concept_ids", []),
                        "usage_type": child.get("usage_type", "explained"),
                        "explanation_depth": child.get("explanation_depth", {}),
                        "max_source_extent": child.get("max_source_extent")
                    }
                    ch["sections"].append(sec)
                chapters.append(ch)
        return chapters

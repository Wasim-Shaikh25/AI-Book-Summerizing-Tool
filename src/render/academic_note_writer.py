import logging
import json
import re
from typing import List, Dict, Any, Optional
from src.core.gemini.async_client import GeminiAsyncClient
from src.core.gemini.prompts.prompts import PROMPT_ACADEMIC_NOTE_WRITER, PROMPT_COMPRESS_EXAMPLE
from src.core.gemini.renderer_profiles import RendererProfile, PROFILES, ExampleHandling
from src.config import REWRITE_MAX_TOKENS
from src.utils.async_manager import AsyncExecutionManager
from src.utils.cpu_manager import CPUExecutionManager
from src.utils.execution_trace import ExecutionTrace

logger = logging.getLogger(__name__)

class AcademicNoteWriter:
    """
    Writes structured, exam-oriented academic notes in Markdown format.
    Ensures no repetition by cross-referencing already explained topics.
    """
    def __init__(self):
        self.client = GeminiAsyncClient()
        self.async_manager = AsyncExecutionManager(max_concurrency=5)
        self.cpu_manager = CPUExecutionManager()

    def _deterministic_compress_cpu(self, example_text: str) -> str:
        """
        CPU-bound deterministic compression using regex and string logic.
        Removes narrative filler while preserving premise and outcome.
        """
        import re
        # Remove common narrative filler
        filler_patterns = [
            r"Imagine a situation where",
            r"Let's say that",
            r"Consider the case of",
            r"For instance, if we look at",
            r"In this story,",
            r"Once upon a time"
        ]
        compressed = example_text
        for pattern in filler_patterns:
            compressed = re.sub(pattern, "", compressed, flags=re.IGNORECASE)
        
        # Simple logic to keep first and last sentences if long
        sentences = re.split(r'(?<=[.!?])\s+', compressed.strip())
        if len(sentences) > 3:
            # Keep premise (first 1-2) and outcome (last 1)
            compressed = sentences[0] + " " + sentences[-1]
            
        return compressed.strip()

    async def _compress_example_async(self, example_text: str) -> str:
        """
        Asynchronously compresses an academic example using Gemini.
        """
        prompt = PROMPT_COMPRESS_EXAMPLE.format(example_text=example_text)
        response = await self.client.generate_content_async(prompt, generation_config={"temperature": 0.1})
        return response.strip() if response else example_text

    def _compress_example(self, example_text: str) -> str:
        """
        Deterministically compresses an academic example using Gemini.
        """
        prompt = PROMPT_COMPRESS_EXAMPLE.format(example_text=example_text)
        response = self.client.generate_content(prompt, generation_config={"temperature": 0.1})
        return response.strip() if response else example_text

    async def write_notes_async(
        self, 
        topic_name: str, 
        node_content: str, 
        explanation_depth: Any, # Can be str or ExplanationDepth object
        relationships: List[Dict[str, str]], 
        already_explained: List[str],
        tagged_examples: List[Dict[str, Any]] = None,
        reference_only_terms: List[str] = None,
        profile: RendererProfile = PROFILES["NOTES_MODE"],
        render_confidence: float = 1.0,
        trace: Optional[ExecutionTrace] = None,
        max_source_extent: Optional[str] = None,
        source_topic_ids: List[str] = None,
        **kwargs # Absorb extra arguments like slot_id
    ) -> Dict[str, Any]:
        """
        Asynchronously generates Markdown notes for a specific topic.
        Returns a dict with 'markdown' and 'flex_actions'.
        """
        # Deterministic Example Compression (CPU-bound parallelization)
        final_examples = []
        if tagged_examples:
            to_compress = []
            for ex in tagged_examples:
                if profile.example_handling == ExampleHandling.COMPRESS_OR_DROP_LOW_RELEVANCE and ex.get("exam_relevance") == "low":
                    continue
                if profile.example_handling == ExampleHandling.COMPRESS_OR_DROP_LOW_RELEVANCE and ex.get("example_type") == "compressible":
                    to_compress.append(ex)
                else:
                    final_examples.append(ex.copy())
            
            if to_compress:
                texts = [e["text"] for e in to_compress]
                compressed_texts = self.cpu_manager.run_parallel(self._deterministic_compress_cpu, texts)
                for ex, ct in zip(to_compress, compressed_texts):
                    new_ex = ex.copy()
                    new_ex["text"] = ct
                    final_examples.append(new_ex)
            processed_examples = final_examples
        else:
            processed_examples = []

        rel_context = ", ".join([f"{r['topic']} ({r['relation']})" for r in relationships]) if relationships else "None identified."
        explained_context = ", ".join(already_explained) if already_explained else "None yet."
        reference_only_context = ", ".join(reference_only_terms) if reference_only_terms else "None identified."
        examples_context = json.dumps(processed_examples, indent=2) if processed_examples else "None provided."

        effective_freedom = profile.content_freedom.value
        if render_confidence < 0.5 and effective_freedom == "allow_enhancement":
            effective_freedom = "restricted"

        # Format explanation depth constraints
        depth_constraints = ""
        if hasattr(explanation_depth, 'dict'):
            d = explanation_depth.dict()
            depth_constraints = (
                f"STRICT DEPTH LIMITS (DO NOT EXCEED):\n"
                f"- Definition: {'Required' if d.get('definition') else 'Forbidden'}\n"
                f"- Intuition/Analogy: {'Allowed' if d.get('intuition') else 'Forbidden'}\n"
                f"- Derivation: {'Allowed' if d.get('derivation') else 'Forbidden'}\n"
                f"- Examples: {d.get('examples', 'none')}\n"
                f"- Proof: {'Allowed' if d.get('proof') else 'Forbidden'}\n"
            )
            if max_source_extent:
                depth_constraints += f"- Max Source Extent: {max_source_extent}\n"
        else:
            depth_constraints = f"Target Depth: {explanation_depth}"

        guard_clause = "None."
        if effective_freedom == "forbidden":
            guard_clause = (
                "STRICT FIDELITY REQUIRED. You are FORBIDDEN from using external knowledge. "
                "If the provided 'NODE CONTENT' is insufficient, you MUST state that information is missing. "
                "Do NOT make inferences. Do NOT add new ideas."
            )
        
        # Add depth enforcement to guard clause
        guard_clause += f"\n{depth_constraints}\nRenderer must NEVER exceed recorded explanation depth."
        
        # Add expansion rules based on profile and allowed_expansion
        expansion_rule = ""
        allowed_exp = getattr(explanation_depth, 'allowed_expansion', 'rephrase_only') if hasattr(explanation_depth, 'allowed_expansion') else 'rephrase_only'
        
        if profile.name == "BOOK_MODE":
            expansion_rule = "RULE: You may rephrase or enhance wording for better flow, but you MUST NOT introduce new concepts or exceed the recorded depth."
        else: # NOTES_MODE or EXAM_NOTES_MODE
            expansion_rule = "RULE: You MUST stay strictly within the source text meaning. DO NOT add any external knowledge, analogies, or enhancements not present in the source."

        if allowed_exp == "rephrase_only":
            expansion_rule += "\nSTRICT RULE: You may ONLY rephrase the source content. DO NOT add any new information."
        elif allowed_exp == "compress":
            expansion_rule += "\nSTRICT RULE: You must compress the content significantly while preserving core meaning."
            
        guard_clause += f"\n{expansion_rule}\nRenderer may ONLY explain content present in mapped SourceBlueprint nodes."
        guard_clause += "\nCRITICAL: NEVER create new headings or subtopics. NEVER explain topics marked as 'referenced_only'."
        
        # ENFORCE REFERENCED_ONLY: If the topic itself is referenced_only, it must not be explained.
        # This is a safety check in case the pipeline accidentally sends a referenced_only topic for writing.
        is_referenced_only = False
        if hasattr(explanation_depth, 'usage_type') and explanation_depth.usage_type == 'referenced_only':
            is_referenced_only = True
        elif isinstance(explanation_depth, str) and 'referenced_only' in explanation_depth.lower():
            is_referenced_only = True
            
        if is_referenced_only:
            logger.warning(f"Topic '{topic_name}' is marked as 'referenced_only'. Rendering as a single mention.")
            return {"markdown": f"*{topic_name}* (Referenced in source text)."}

        prompt = PROMPT_ACADEMIC_NOTE_WRITER.format(
            topic_name=topic_name,
            node_content=node_content,
            explanation_depth=depth_constraints,
            topic_relationships=rel_context,
            already_explained_topics=explained_context,
            reference_only_context=reference_only_context,
            tagged_examples=examples_context,
            profile_name=profile.name,
            bullet_ratio=profile.bullet_ratio,
            prose_ratio=profile.prose_ratio,
            example_handling=profile.example_handling.value,
            content_freedom=effective_freedom,
            guard_clause=guard_clause
        )

        raw_response = await self.client.generate(
            prompt=prompt,
            trace=trace,
            task_name=f"write_notes:{topic_name}",
            generation_config={"temperature": 0.7, "max_output_tokens": REWRITE_MAX_TOKENS * 2}
        )

        if not raw_response or not isinstance(raw_response, str):
            return {"markdown": ""}

        # CLEANUP: Aggressively strip any headings generated by the LLM
        # This allows us to recover from minor LLM "authorial" drift while still enforcing the rule.
        cleaned_markdown = re.sub(r'^#+.*?\n', '', raw_response, flags=re.MULTILINE).strip()

        # RUNTIME ASSERTION: AcademicNoteWriter never changes structure
        # If after stripping we still find structural markers, we crash.
        if re.search(r'^#+\s+', cleaned_markdown, re.MULTILINE):
            error_msg = f"CRITICAL ARCHITECTURAL VIOLATION: AcademicNoteWriter attempted to generate structural headings for topic '{topic_name}' that could not be safely stripped."
            logger.error(error_msg)
            raise AssertionError(error_msg)

        # Log rendering stats if trace is provided
        if trace:
            # Heuristic for depth consumed
            depth_consumed = {
                "definition": "definition" in raw_response.lower(),
                "intuition": any(w in raw_response.lower() for w in ["imagine", "analogy", "intuition"]),
                "derivation": any(w in raw_response.lower() for w in ["derived", "formula", "equation"]),
                "examples": "brief" if "example" in raw_response.lower() else "none",
                "proof": "proof" in raw_response.lower()
            }
            
            allowed_dict = explanation_depth.dict() if hasattr(explanation_depth, 'dict') else {"target": str(explanation_depth)}
            
            trace.log_rendering_stats(
                topic_id=topic_name,
                source_ids=source_topic_ids or [],
                depth_allowed=allowed_dict,
                depth_consumed=depth_consumed
            )

        # AcademicNoteWriter is now a pure RENDERER.
        # Structural FLEX actions (RENAME, MERGE, SPLIT) have been removed.
        markdown_content = raw_response

        # Remove any accidental JSON blocks if the LLM still generates them
        try:
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
            if json_match:
                markdown_content = raw_response[json_match.end():].strip()
            elif raw_response.strip().startswith('{'):
                brace_count = 0
                end_pos = -1
                for i, char in enumerate(raw_response):
                    if char == '{': brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_pos = i + 1
                            break
                if end_pos != -1:
                    markdown_content = raw_response[end_pos:].strip()
        except:
            pass

        return {"markdown": markdown_content}

    def write_notes(
        self, 
        topic_name: str, 
        node_content: str, 
        explanation_depth: str, 
        relationships: List[Dict[str, str]], 
        already_explained: List[str],
        tagged_examples: List[Dict[str, Any]] = None,
        reference_only_terms: List[str] = None,
        profile: RendererProfile = PROFILES["NOTES_MODE"],
        render_confidence: float = 1.0
    ) -> Dict[str, Any]:
        """
        Generates Markdown notes for a specific topic (Synchronous wrapper).
        """
        logger.info(f"Writing content for topic: {topic_name} (Profile: {profile.name}, Confidence: {render_confidence})")
        return self.async_manager.run_single(
            self.write_notes_async,
            args=(topic_name, node_content, explanation_depth, relationships, 
                already_explained, tagged_examples, reference_only_terms, profile, render_confidence)
        )

    def write_notes_batch(self, tasks: List[Dict[str, Any]], trace: Optional[ExecutionTrace] = None) -> List[Dict[str, Any]]:
        """
        Generates notes for multiple topics in parallel.
        """
        logger.info(f"Writing content for {len(tasks)} topics in parallel...")
        task_names = [f"write_notes:{t['topic_name']}" for t in tasks]
        task_defs = [(self.write_notes_async, (), {**t, "trace": trace}) for t in tasks]
        return self.async_manager.run_parallel(task_defs, task_names=task_names)

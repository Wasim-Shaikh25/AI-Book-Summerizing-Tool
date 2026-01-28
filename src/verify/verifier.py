import logging
import json
import re
import asyncio
from typing import Dict, Any, Optional
from src.core.gemini.client import GeminiClient
from src.core.gemini.prompts.prompts import PROMPT_VERIFY_OUTPUT
from src.core.gemini.renderer_profiles import RendererProfile
from src.utils.execution_trace import ExecutionTrace

logger = logging.getLogger(__name__)

class VerifierAgent:
    """
    Verifies generated output against the Knowledge Blueprint and Renderer Profile.
    Ensures strict adherence to structural integrity, content limits, and expansion rules.
    
    STRICT RULE: This agent must execute in a single-threaded, synchronous context.
    """
    def __init__(self):
        self.client = GeminiClient()

    def verify(
        self, 
        generated_output: str, 
        blueprint_context: str, 
        profile: RendererProfile,
        trace: Optional[ExecutionTrace] = None
    ) -> Dict[str, Any]:
        """
        Performs a QA check on the generated content (Strictly Synchronous).
        """
        # Runtime Assertion: Ensure not in an async context
        try:
            asyncio.get_running_loop()
            raise RuntimeError("CRITICAL SAFETY VIOLATION: VerifierAgent must NOT be called from an asynchronous context.")
        except RuntimeError as e:
            if "no running event loop" not in str(e):
                raise e

        logger.info(f"Verifying output against profile: {profile.name} for structural and content integrity.")
        
        profile_context = json.dumps(profile.dict(), indent=2)
        
        prompt = PROMPT_VERIFY_OUTPUT.format(
            blueprint_context=blueprint_context,
            profile_context=profile_context,
            generated_output=generated_output
        )
        
        # Use synchronous client
        response = self.client.generate_content(
            prompt=prompt,
            generation_config={"temperature": 0.1}
        )
        
        result = self._parse_verification(response, profile.name)
        
        if trace:
            trace.log_stage(
                agent="VerifierAgent",
                action=f"verify_output:{profile.name}",
                confidence=result.get("confidence", 0.0),
                status="passed" if result.get("valid") else "failed"
            )
            
        return result

    def _parse_verification(self, response: str, profile_name: str) -> Dict[str, Any]:
        if not response:
            return {"valid": False, "reason": "Verifier failed to respond.", "violations": [], "confidence": 0.0}

        try:
            # Clean response if it contains markdown fences
            clean_response = re.sub(r'```json\s*|\s*```', '', response).strip()
            # Robust JSON parsing
            start_idx = clean_response.find('{')
            end_idx = clean_response.rfind('}')
            if start_idx != -1 and end_idx != -1:
                clean_response = clean_response[start_idx:end_idx+1]
                
            result = json.loads(clean_response)
            
            # ENFORCE HARD INVARIANCES
            stats = result.get("stats", {})
            violations = result.get("violations", [])
            
            # 1. Topic Count Invariance
            if stats.get("blueprint_topic_count") != stats.get("rendered_topic_count"):
                if "TOPIC_COUNT_MISMATCH" not in violations:
                    violations.append("TOPIC_COUNT_MISMATCH")
                result["valid"] = False
                
            # 2. Depth Invariance
            if stats.get("blueprint_depth") != stats.get("rendered_depth"):
                if "DEPTH_INCREASED" not in violations:
                    violations.append("DEPTH_INCREASED")
                result["valid"] = False

            # RUNTIME ASSERTION: Verifier blocks all violations
            # If the verifier detects a violation but still marks it as valid, we crash.
            if violations and result.get("valid"):
                error_msg = f"CRITICAL ARCHITECTURAL VIOLATION: Verifier detected violations {violations} but marked output as valid."
                logger.error(error_msg)
                raise AssertionError(error_msg)

            if result.get("valid"):
                logger.info(f"Output verification PASSED for profile: {profile_name}")
            else:
                logger.warning(f"Output verification FAILED for profile: {profile_name}: {result.get('reason')}")
                logger.warning(f"Violations detected: {violations}")
                logger.warning(f"Stats: {stats}")
                
            result["violations"] = violations
            return result
        except Exception as e:
            logger.error(f"Failed to parse verification result: {e}")
            return {"valid": False, "reason": f"Parsing error: {str(e)}", "violations": [], "confidence": 0.0}

import logging
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class ExecutionTrace:
    """
    Lightweight execution trace logger for multi-agent pipeline debugging and QA.
    """
    def __init__(self):
        self.trace: List[Dict[str, Any]] = []

    def log_stage(
        self, 
        agent: str, 
        action: str, 
        confidence: float = 1.0, 
        status: str = "passed",
        task_name: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        retry_count: int = 0
    ):
        """
        Logs a single stage of the pipeline with extended metadata.
        """
        entry = {
            "stage": agent,
            "action": action,
            "task_name": task_name,
            "confidence": round(confidence, 2),
            "status": status,
            "start_time": start_time,
            "end_time": end_time or datetime.utcnow().isoformat(),
            "retry_count": retry_count
        }
        self.trace.append(entry)
        logger.info(f"[TRACE] {agent}: {action} | Status: {status} | Confidence: {confidence} | Retries: {retry_count}")

    def log_flex_action(self, agent: str, action_type: str, details: Dict[str, Any]):
        """
        Logs a FLEX action (RENAME, MERGE, SPLIT) taken by an agent.
        """
        entry = {
            "stage": agent,
            "action": "FLEX_ACTION",
            "type": action_type,
            "details": details,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.trace.append(entry)
        logger.info(f"[TRACE] {agent}: FLEX_ACTION | Type: {action_type} | Details: {json.dumps(details, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o))}")

    def log_blueprint_usage(self, blueprint_type: str, details: Dict[str, Any]):
        """
        Logs which blueprint was used and any structural restrictions applied.
        """
        entry = {
            "stage": "Pipeline",
            "action": "BLUEPRINT_USAGE",
            "blueprint_type": blueprint_type,
            "details": details,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.trace.append(entry)
        logger.info(f"[TRACE] Blueprint Used: {blueprint_type} | Restrictions: {json.dumps(details, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o))}")

    def log_rendering_stats(self, topic_id: str, source_ids: List[str], depth_allowed: Dict[str, Any], depth_consumed: Dict[str, Any]):
        """
        Logs rendering statistics for a topic, including depth consumed vs allowed.
        """
        entry = {
            "stage": "AcademicNoteWriter",
            "action": "RENDERING_STATS",
            "topic_id": topic_id,
            "source_topic_ids": source_ids,
            "depth_allowed": depth_allowed,
            "depth_consumed": depth_consumed,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.trace.append(entry)
        logger.info(f"[TRACE] Rendered Topic: {topic_id} | Source IDs: {source_ids} | Depth Consumed: {json.dumps(depth_consumed, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o))}")

    def log_structural_violation(self, violation_type: str, details: Dict[str, Any]):
        """
        Logs a structural violation (e.g., attempted_new_topic, attempted_depth_increase).
        """
        entry = {
            "stage": "VerifierAgent",
            "action": "STRUCTURAL_VIOLATION",
            "violation_type": violation_type,
            "details": details,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.trace.append(entry)
        logger.warning(f"[TRACE] STRUCTURAL VIOLATION: {violation_type} | Details: {json.dumps(details, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o))}")

    def log_rejected_render(self, reason: str, stats: Dict[str, Any]):
        """
        Logs why a rendered output was rejected.
        """
        entry = {
            "stage": "Pipeline",
            "action": "REJECTED_RENDER",
            "reason": reason,
            "stats": stats,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.trace.append(entry)
        logger.error(f"[TRACE] RENDER REJECTED: {reason} | Stats: {json.dumps(stats, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o))}")

    def get_trace(self) -> List[Dict[str, Any]]:
        """Returns the full execution trace."""
        return self.trace

    def clear(self):
        """Clears the trace."""
        self.trace = []

    def to_json(self) -> str:
        """Returns the trace as a JSON string."""
        return json.dumps(self.trace, indent=2, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o))

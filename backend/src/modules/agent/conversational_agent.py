"""Conversational agent interface - main entry point for agentic system."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import logging

from .tool_registry import ToolRegistry, get_tool_registry
from .planner_agent import PlannerAgent, ExecutionPlan
from .executor_agent import ExecutorAgent, ExecutionResult
from .state_manager import StateManager, get_state_manager, ConversationMessage

logger = logging.getLogger(__name__)


class AgentResponse(BaseModel):
    """Response from the conversational agent."""
    message: str
    plan_id: Optional[str] = None
    execution_result: Optional[ExecutionResult] = None
    requires_action: bool = False
    action_type: Optional[str] = None
    action_details: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConversationalAgent:
    """Main conversational agent that orchestrates planning and execution."""
    
    def __init__(self):
        self.tool_registry = get_tool_registry()
        self.planner = PlannerAgent(self.tool_registry)
        self.executor = ExecutorAgent(self.tool_registry)
        self.state_manager = get_state_manager()
        self.user_id = "default_user"  # Would come from authentication
    
    def process_message(self, user_message: str, conversation_id: Optional[str] = None) -> AgentResponse:
        """Process a user message through the agentic system."""
        logger.info(f"Processing message: {user_message[:100]}...")
        
        # Get or create conversation
        if not conversation_id:
            conversation = self.state_manager.create_conversation(self.user_id)
            conversation_id = conversation.conversation_id
        else:
            conversation = self.state_manager.get_conversation(conversation_id)
            if not conversation:
                conversation = self.state_manager.create_conversation(self.user_id)
                conversation_id = conversation.conversation_id
        
        # Add user message to conversation
        self.state_manager.add_message(conversation_id, "user", user_message)
        
        # Get context for planning
        context = self.state_manager.get_context_for_planning(self.user_id)
        
        # Create execution plan
        try:
            plan = self.planner.create_plan(user_message, context)
            logger.info(f"Created plan: {plan.plan_id} with {len(plan.steps)} steps")
            
            # Add system message about plan
            plan_message = f"Created plan: {plan.reasoning}"
            self.state_manager.add_message(conversation_id, "system", plan_message, {"plan_id": plan.plan_id})
            
            # Check if plan requires user input
            if plan.requires_user_input:
                return AgentResponse(
                    message=f"I need some information to proceed: {', '.join(plan.missing_information)}",
                    plan_id=plan.plan_id,
                    requires_action=True,
                    action_type="user_input",
                    action_details={"missing_information": plan.missing_information},
                    metadata={"plan": plan.dict()}
                )
            
            # Execute the plan
            execution_result = self.executor.execute_plan(plan)
            
            # Add execution result to conversation state
            self.state_manager.update_conversation_state(
                conversation_id, 
                "last_execution_result", 
                execution_result.dict()
            )
            
            # Generate response message
            response_message = self._generate_response_message(execution_result, plan)
            
            # Add assistant response to conversation
            self.state_manager.add_message(conversation_id, "assistant", response_message, {
                "plan_id": plan.plan_id,
                "execution_status": execution_result.status
            })
            
            return AgentResponse(
                message=response_message,
                plan_id=plan.plan_id,
                execution_result=execution_result,
                metadata={"plan": plan.dict()}
            )
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            error_message = f"I encountered an error while processing your request: {str(e)}"
            self.state_manager.add_message(conversation_id, "assistant", error_message, {"error": str(e)})
            
            return AgentResponse(
                message=error_message,
                requires_action=False,
                metadata={"error": str(e)}
            )
    
    def upload_document(self, file_path: str, file_name: str, file_type: str, conversation_id: Optional[str] = None) -> AgentResponse:
        """Handle document upload."""
        logger.info(f"Document upload: {file_name}")
        
        # Register document
        document = self.state_manager.register_document(file_path, file_name, file_type, self.user_id)
        
        # Add to conversation if provided
        if conversation_id:
            self.state_manager.add_message(
                conversation_id, 
                "system", 
                f"Document uploaded: {file_name}",
                {"document_id": document.document_id, "file_path": file_path}
            )
        
        return AgentResponse(
            message=f"Document '{file_name}' uploaded successfully. I can now process this document.",
            requires_action=False,
            action_details={"document_id": document.document_id}
        )
    
    def get_conversation_history(self, conversation_id: str) -> List[ConversationMessage]:
        """Get conversation history."""
        return self.state_manager.get_conversation_messages(conversation_id)
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools for information."""
        return self.tool_registry.get_tool_schema()
    
    def _generate_response_message(self, execution_result: ExecutionResult, plan: ExecutionPlan) -> str:
        """Generate a natural language response from execution results."""
        if execution_result.status == "completed":
            # Success response
            if execution_result.final_output:
                final_result = execution_result.final_output
                
                # Tailor response based on plan type
                if "study_guide" in plan.plan_id.lower():
                    return f"I've successfully created your study guide! {execution_result.steps_completed} steps were completed. The guide is ready for download."
                elif "qa" in plan.plan_id.lower():
                    answers = final_result.get("final_result", {})
                    return f"I've answered your questions using the available documents. {execution_result.steps_completed} questions were processed."
                elif "doc_processing" in plan.plan_id.lower():
                    return f"I've successfully processed your document(s). {execution_result.steps_completed} document(s) are now ready for questions and analysis."
                else:
                    return f"I've completed your request successfully. {execution_result.steps_completed} steps were executed."
            else:
                return f"I've completed your request. {execution_result.steps_completed} steps were executed."
        
        elif execution_result.status == "failed":
            # Failure response
            if execution_result.errors:
                error_summary = execution_result.errors[:2]  # First 2 errors
                return f"I encountered some issues: {'; '.join(error_summary)}. Some steps may not have completed."
            else:
                return "I encountered an unexpected error while processing your request."
        
        else:
            return "I'm still processing your request. Please wait a moment."
    
    def handle_followup(self, user_message: str, conversation_id: str) -> AgentResponse:
        """Handle follow-up questions in an existing conversation."""
        # Get conversation context
        messages = self.get_conversation_history(conversation_id)
        context = {
            "conversation_history": [msg.dict() for msg in messages[-5:]],  # Last 5 messages
            "execution_state": self.state_manager.get_conversation(conversation_id).execution_state
        }
        
        # Process with enhanced context
        return self.process_message(user_message, conversation_id)


# Global agent instance
_conversational_agent = None

def get_conversational_agent() -> ConversationalAgent:
    """Get the global conversational agent instance."""
    global _conversational_agent
    if _conversational_agent is None:
        _conversational_agent = ConversationalAgent()
    return _conversational_agent

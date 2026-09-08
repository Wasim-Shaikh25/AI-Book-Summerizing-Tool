"""State management for agentic system - handles multi-document workflows and conversation context."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import json
import uuid


class DocumentInfo(BaseModel):
    """Information about a document in the system."""
    document_id: str
    file_path: str
    file_name: str
    file_type: str
    upload_time: datetime
    status: str  # uploaded, processing, processed, failed
    book_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConversationMessage(BaseModel):
    """A message in the conversation."""
    message_id: str
    role: str  # user, assistant, system
    content: str
    timestamp: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConversationState(BaseModel):
    """State of a conversation with the agent."""
    conversation_id: str
    user_id: str
    messages: List[ConversationMessage] = Field(default_factory=list)
    current_plan_id: Optional[str] = None
    execution_state: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class WorkflowState(BaseModel):
    """State of a multi-document workflow."""
    workflow_id: str
    user_id: str
    workflow_type: str  # study_guide, multi_doc_analysis, etc.
    status: str  # pending, in_progress, completed, failed
    documents: List[DocumentInfo] = Field(default_factory=list)
    steps_completed: List[str] = Field(default_factory=list)
    steps_remaining: List[str] = Field(default_factory=list)
    intermediate_results: Dict[str, Any] = Field(default_factory=dict)
    final_output: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class StateManager:
    """Manages state for conversations and workflows."""
    
    def __init__(self):
        self.conversations: Dict[str, ConversationState] = {}
        self.workflows: Dict[str, WorkflowState] = {}
        self.documents: Dict[str, DocumentInfo] = {}
    
    def create_conversation(self, user_id: str) -> ConversationState:
        """Create a new conversation."""
        conversation_id = str(uuid.uuid4())
        conversation = ConversationState(
            conversation_id=conversation_id,
            user_id=user_id
        )
        self.conversations[conversation_id] = conversation
        return conversation
    
    def get_conversation(self, conversation_id: str) -> Optional[ConversationState]:
        """Get a conversation by ID."""
        return self.conversations.get(conversation_id)
    
    def add_message(self, conversation_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[ConversationMessage]:
        """Add a message to a conversation."""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return None
        
        message = ConversationMessage(
            message_id=str(uuid.uuid4()),
            role=role,
            content=content,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )
        conversation.messages.append(message)
        conversation.updated_at = datetime.now()
        return message
    
    def get_conversation_messages(self, conversation_id: str) -> List[ConversationMessage]:
        """Get all messages in a conversation."""
        conversation = self.get_conversation(conversation_id)
        return conversation.messages if conversation else []
    
    def update_conversation_state(self, conversation_id: str, key: str, value: Any) -> bool:
        """Update conversation execution state."""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return False
        
        conversation.execution_state[key] = value
        conversation.updated_at = datetime.now()
        return True
    
    def register_document(self, file_path: str, file_name: str, file_type: str, user_id: str) -> DocumentInfo:
        """Register a document in the system."""
        document_id = str(uuid.uuid4())
        document = DocumentInfo(
            document_id=document_id,
            file_path=file_path,
            file_name=file_name,
            file_type=file_type,
            upload_time=datetime.now(),
            status="uploaded"
        )
        self.documents[document_id] = document
        return document
    
    def update_document_status(self, document_id: str, status: str, book_id: Optional[str] = None) -> bool:
        """Update document processing status."""
        document = self.documents.get(document_id)
        if not document:
            return False
        
        document.status = status
        if book_id:
            document.book_id = book_id
        return True
    
    def get_user_documents(self, user_id: str) -> List[DocumentInfo]:
        """Get all documents for a user."""
        # For now, return all documents (would filter by user_id in production)
        return list(self.documents.values())
    
    def get_processed_documents(self) -> List[DocumentInfo]:
        """Get all successfully processed documents."""
        return [doc for doc in self.documents.values() if doc.status == "processed" and doc.book_id]
    
    def create_workflow(self, user_id: str, workflow_type: str, document_ids: List[str]) -> WorkflowState:
        """Create a new workflow."""
        workflow_id = str(uuid.uuid4())
        
        documents = [self.documents[doc_id] for doc_id in document_ids if doc_id in self.documents]
        
        workflow = WorkflowState(
            workflow_id=workflow_id,
            user_id=user_id,
            workflow_type=workflow_type,
            status="pending",
            documents=documents
        )
        self.workflows[workflow_id] = workflow
        return workflow
    
    def update_workflow_status(self, workflow_id: str, status: str) -> bool:
        """Update workflow status."""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return False
        
        workflow.status = status
        workflow.updated_at = datetime.now()
        return True
    
    def add_workflow_step_result(self, workflow_id: str, step_id: str, result: Any) -> bool:
        """Add result of a workflow step."""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return False
        
        workflow.steps_completed.append(step_id)
        workflow.intermediate_results[step_id] = result
        workflow.updated_at = datetime.now()
        return True
    
    def set_workflow_output(self, workflow_id: str, output: Dict[str, Any]) -> bool:
        """Set final output of a workflow."""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return False
        
        workflow.final_output = output
        workflow.status = "completed"
        workflow.updated_at = datetime.now()
        return True
    
    def get_workflow(self, workflow_id: str) -> Optional[WorkflowState]:
        """Get a workflow by ID."""
        return self.workflows.get(workflow_id)
    
    def get_user_workflows(self, user_id: str) -> List[WorkflowState]:
        """Get all workflows for a user."""
        return [wf for wf in self.workflows.values() if wf.user_id == user_id]
    
    def get_context_for_planning(self, user_id: str) -> Dict[str, Any]:
        """Get context for the planner agent."""
        return {
            "uploaded_documents": [
                {
                    "document_id": doc.document_id,
                    "path": doc.file_path,
                    "name": doc.file_name,
                    "status": doc.status,
                    "book_id": doc.book_id
                }
                for doc in self.get_user_documents(user_id)
            ],
            "existing_documents": [
                {
                    "document_id": doc.document_id,
                    "name": doc.file_name,
                    "book_id": doc.book_id
                }
                for doc in self.get_processed_documents()
            ],
            "recent_workflows": [
                {
                    "workflow_id": wf.workflow_id,
                    "type": wf.workflow_type,
                    "status": wf.status
                }
                for wf in self.get_user_workflows(user_id)[-5:]  # Last 5 workflows
            ]
        }
    
    def cleanup_old_state(self, max_age_hours: int = 24) -> int:
        """Clean up old state to prevent memory bloat."""
        cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
        
        # Clean up old conversations
        old_conversations = [
            conv_id for conv_id, conv in self.conversations.items()
            if conv.updated_at.timestamp() < cutoff_time
        ]
        for conv_id in old_conversations:
            del self.conversations[conv_id]
        
        # Clean up old workflows
        old_workflows = [
            wf_id for wf_id, wf in self.workflows.items()
            if wf.updated_at.timestamp() < cutoff_time
        ]
        for wf_id in old_workflows:
            del self.workflows[wf_id]
        
        return len(old_conversations) + len(old_workflows)


# Global state manager instance
_state_manager = None

def get_state_manager() -> StateManager:
    """Get the global state manager instance."""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager

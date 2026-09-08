"""Planner agent for decomposing user requests into executable steps."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum

from .tool_registry import ToolRegistry, ToolDefinition


class StepType(str, Enum):
    """Types of execution steps."""
    TOOL_CALL = "tool_call"
    CONDITIONAL = "conditional"
    PARALLEL = "parallel"
    LOOP = "loop"


class ExecutionStep(BaseModel):
    """Single execution step in the plan."""
    step_id: str
    step_type: StepType
    tool_name: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)
    description: str
    expected_output: Optional[str] = None


class ExecutionPlan(BaseModel):
    """Complete execution plan for a user request."""
    plan_id: str
    user_request: str
    steps: List[ExecutionStep]
    estimated_steps: int
    reasoning: str
    requires_user_input: bool = False
    missing_information: List[str] = Field(default_factory=list)


class PlannerAgent:
    """Agent that decomposes user requests into execution plans."""
    
    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry
        self.planner_llm = None  # Will be configured with GPT-4/Claude
    
    def create_plan(self, user_request: str, context: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
        """Create an execution plan from a user request."""
        context = context or {}
        
        # Get available tools
        available_tools = self.tool_registry.list_tools()
        tool_schemas = self.tool_registry.get_tool_schema()
        
        # Analyze the request and create plan
        plan = self._analyze_and_plan(user_request, available_tools, context)
        
        return plan
    
    def _analyze_and_plan(self, user_request: str, available_tools: List[ToolDefinition], context: Dict[str, Any]) -> ExecutionPlan:
        """Analyze request and create execution plan."""
        # Check for uploaded documents in context
        uploaded_documents = context.get("uploaded_documents", [])
        existing_documents = context.get("existing_documents", [])
        
        # Determine the type of request
        request_type = self._classify_request(user_request)
        
        # Generate plan based on request type
        if request_type == "document_processing":
            return self._create_document_processing_plan(user_request, uploaded_documents, context)
        elif request_type == "question_answering":
            return self._create_qa_plan(user_request, existing_documents, context)
        elif request_type == "multi_document_analysis":
            return self._create_multi_doc_plan(user_request, uploaded_documents, existing_documents, context)
        elif request_type == "study_guide_creation":
            return self._create_study_guide_plan(user_request, uploaded_documents, existing_documents, context)
        else:
            return self._create_generic_plan(user_request, available_tools, context)
    
    def _classify_request(self, user_request: str) -> str:
        """Classify the type of user request."""
        request_lower = user_request.lower()
        
        if any(keyword in request_lower for keyword in ["process", "upload", "pdf", "document"]):
            return "document_processing"
        elif any(keyword in request_lower for keyword in ["question", "answer", "explain"]):
            return "question_answering"
        elif any(keyword in request_lower for keyword in ["compare", "multiple", "cross-reference", "analyze"]):
            return "multi_document_analysis"
        elif any(keyword in request_lower for keyword in ["study guide", "notes", "summary", "prepare"]):
            return "study_guide_creation"
        else:
            return "generic"
    
    def _create_document_processing_plan(self, user_request: str, uploaded_documents: List[Dict], context: Dict) -> ExecutionPlan:
        """Create plan for document processing requests."""
        steps = []
        
        if not uploaded_documents:
            # Plan to ask for document upload
            return ExecutionPlan(
                plan_id="need_upload",
                user_request=user_request,
                steps=[],
                estimated_steps=0,
                reasoning="No documents provided. User needs to upload documents first.",
                requires_user_input=True,
                missing_information=["PDF documents to process"]
            )
        
        # Process each uploaded document
        for i, doc in enumerate(uploaded_documents):
            step = ExecutionStep(
                step_id=f"process_doc_{i}",
                step_type=StepType.TOOL_CALL,
                tool_name="process_pdf",
                parameters={
                    "pdf_path": doc.get("path"),
                    "user_instruction": user_request,
                    "ingestion_profile": "fast_local"
                },
                description=f"Process document: {doc.get('name', 'Unknown')}",
                expected_output="book_id"
            )
            steps.append(step)
        
        return ExecutionPlan(
            plan_id="doc_processing",
            user_request=user_request,
            steps=steps,
            estimated_steps=len(steps),
            reasoning=f"Process {len(uploaded_documents)} uploaded document(s) through the pipeline"
        )
    
    def _create_qa_plan(self, user_request: str, existing_documents: List[Dict], context: Dict) -> ExecutionPlan:
        """Create plan for question answering requests."""
        steps = []
        
        if not existing_documents:
            return ExecutionPlan(
                plan_id="need_documents",
                user_request=user_request,
                steps=[],
                estimated_steps=0,
                reasoning="No processed documents available for Q&A.",
                requires_user_input=True,
                missing_information=["Processed documents to search"]
            )
        
        # Extract questions from user request
        questions = self._extract_questions(user_request)
        
        for i, question in enumerate(questions):
            step = ExecutionStep(
                step_id=f"answer_q_{i}",
                step_type=StepType.TOOL_CALL,
                tool_name="answer_questions",
                parameters={
                    "questions": [question],
                    "book_id": existing_documents[0].get("book_id"),  # Use first document
                    "depth": "detailed"
                },
                description=f"Answer question: {question[:50]}...",
                expected_output="answer"
            )
            steps.append(step)
        
        return ExecutionPlan(
            plan_id="qa_plan",
            user_request=user_request,
            steps=steps,
            estimated_steps=len(steps),
            reasoning=f"Answer {len(questions)} question(s) using available documents"
        )
    
    def _create_multi_doc_plan(self, user_request: str, uploaded_docs: List[Dict], existing_docs: List[Dict], context: Dict) -> ExecutionPlan:
        """Create plan for multi-document analysis."""
        steps = []
        
        # Process uploaded documents first
        for i, doc in enumerate(uploaded_docs):
            step = ExecutionStep(
                step_id=f"process_doc_{i}",
                step_type=StepType.TOOL_CALL,
                tool_name="process_pdf",
                parameters={
                    "pdf_path": doc.get("path"),
                    "user_instruction": "create comprehensive notes"
                },
                description=f"Process document: {doc.get('name', 'Unknown')}",
                expected_output="book_id"
            )
            steps.append(step)
        
        # Analyze topics across all documents
        all_book_ids = [d.get("book_id") for d in existing_docs] + [f"doc_{i}" for i in range(len(uploaded_docs))]
        
        analysis_step = ExecutionStep(
            step_id="analyze_topics",
            step_type=StepType.TOOL_CALL,
            tool_name="analyze_topics",
            parameters={
                "book_ids": all_book_ids,
                "analysis_type": "topic_frequency"
            },
            depends_on=[f"process_doc_{i}" for i in range(len(uploaded_docs))],
            description="Analyze topics across all documents",
            expected_output="topic_analysis"
        )
        steps.append(analysis_step)
        
        return ExecutionPlan(
            plan_id="multi_doc_analysis",
            user_request=user_request,
            steps=steps,
            estimated_steps=len(steps),
            reasoning="Process new documents and analyze topics across all documents"
        )
    
    def _create_study_guide_plan(self, user_request: str, uploaded_docs: List[Dict], existing_docs: List[Dict], context: Dict) -> ExecutionPlan:
        """Create plan for study guide generation."""
        steps = []
        
        # Check for question papers
        question_papers = [d for d in uploaded_docs + existing_docs if "question" in d.get("name", "").lower()]
        content_docs = [d for d in uploaded_docs + existing_docs if "question" not in d.get("name", "").lower()]
        
        if not content_docs:
            return ExecutionPlan(
                plan_id="need_content",
                user_request=user_request,
                steps=[],
                estimated_steps=0,
                reasoning="No content documents available for study guide creation.",
                requires_user_input=True,
                missing_information=["Content documents (textbooks, notes)"]
            )
        
        # Process content documents
        for i, doc in enumerate(content_docs):
            if doc in uploaded_docs:  # Only process if not already processed
                step = ExecutionStep(
                    step_id=f"process_content_{i}",
                    step_type=StepType.TOOL_CALL,
                    tool_name="process_pdf",
                    parameters={
                        "pdf_path": doc.get("path"),
                        "user_instruction": "create comprehensive study notes"
                    },
                    description=f"Process content: {doc.get('name', 'Unknown')}",
                    expected_output="book_id"
                )
                steps.append(step)
        
        # Analyze question papers if available
        if question_papers:
            for i, qp in enumerate(question_papers):
                if qp in uploaded_docs:
                    step = ExecutionStep(
                        step_id=f"process_qp_{i}",
                        step_type=StepType.TOOL_CALL,
                        tool_name="process_pdf",
                        parameters={
                            "pdf_path": qp.get("path"),
                            "user_instruction": "extract questions and topics"
                        },
                        description=f"Process question paper: {qp.get('name', 'Unknown')}",
                        expected_output="book_id"
                    )
                    steps.append(step)
        
        # Generate questions based on content
        content_book_ids = [d.get("book_id") for d in content_docs if d.get("book_id")]
        for book_id in content_book_ids:
            step = ExecutionStep(
                step_id=f"generate_questions_{book_id}",
                step_type=StepType.TOOL_CALL,
                tool_name="generate_questions",
                parameters={
                    "book_id": book_id,
                    "question_type": "10-mark",
                    "num_questions": 20
                },
                description=f"Generate questions from content",
                expected_output="questions"
            )
            steps.append(step)
        
        # Export study guide
        export_step = ExecutionStep(
            step_id="export_study_guide",
            step_type=StepType.TOOL_CALL,
            tool_name="export_document",
            parameters={
                "book_id": content_book_ids[0] if content_book_ids else "unknown",
                "format": "docx",
                "output_path": "study_guide.docx"
            },
            depends_on=[f"generate_questions_{bid}" for bid in content_book_ids],
            description="Export compiled study guide",
            expected_output="study_guide_file"
        )
        steps.append(export_step)
        
        return ExecutionPlan(
            plan_id="study_guide_creation",
            user_request=user_request,
            steps=steps,
            estimated_steps=len(steps),
            reasoning="Process content documents, analyze question papers, generate relevant questions, and compile study guide"
        )
    
    def _create_generic_plan(self, user_request: str, available_tools: List[ToolDefinition], context: Dict) -> ExecutionPlan:
        """Create a generic plan using available tools."""
        # This would use LLM to intelligently plan
        # For now, create a simple search-based plan
        
        step = ExecutionStep(
            step_id="search_documents",
            step_type=StepType.TOOL_CALL,
            tool_name="search_documents",
            parameters={
                "query": user_request,
                "top_k": 5
            },
            description="Search documents for relevant information",
            expected_output="search_results"
        )
        
        return ExecutionPlan(
            plan_id="generic_search",
            user_request=user_request,
            steps=[step],
            estimated_steps=1,
            reasoning="Search for relevant information to address the request"
        )
    
    def _extract_questions(self, text: str) -> List[str]:
        """Extract questions from text."""
        # Simple extraction - would be enhanced with NLP
        questions = []
        sentences = text.split('.')
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence.endswith('?') or any(keyword in sentence.lower() for keyword in ["what", "how", "why", "explain", "describe"]):
                questions.append(sentence)
        
        return questions[:5] if questions else [text]  # Limit to 5 questions

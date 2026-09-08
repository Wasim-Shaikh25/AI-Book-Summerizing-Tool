"""Tool registry for agentic AI system - wraps pipeline operations as typed tools."""

import os
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum


class ToolCategory(str, Enum):
    """Categories of tools available to the agent."""
    DOCUMENT_PROCESSING = "document_processing"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    CONTENT_GENERATION = "content_generation"
    ANALYSIS = "analysis"
    EXPORT = "export"


class ToolParameter(BaseModel):
    """Definition of a tool parameter."""
    name: str
    type: str
    description: str
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[List[str]] = None


class ToolDefinition(BaseModel):
    """Complete definition of a tool."""
    name: str
    description: str
    category: ToolCategory
    parameters: List[ToolParameter]
    function: Callable
    requires_context: bool = False  # Whether tool needs conversation context


class ToolRegistry:
    """Registry of available tools for the agentic system."""
    
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_core_tools()
    
    def _register_core_tools(self):
        """Register core pipeline tools."""
        # Document processing tools
        self.register(
            ToolDefinition(
                name="process_pdf",
                description="Process a PDF document through the ingestion pipeline",
                category=ToolCategory.DOCUMENT_PROCESSING,
                parameters=[
                    ToolParameter(
                        name="pdf_path",
                        type="string",
                        description="Path to the PDF file to process",
                        required=True
                    ),
                    ToolParameter(
                        name="user_instruction",
                        type="string",
                        description="User's instruction for processing (e.g., 'create study notes')",
                        required=False,
                        default="create comprehensive notes"
                    ),
                    ToolParameter(
                        name="ingestion_profile",
                        type="string",
                        description="Processing profile (fast_local, accurate, etc.)",
                        required=False,
                        default="fast_local",
                        enum=["fast_local", "accurate", "balanced"]
                    )
                ],
                function=self._process_pdf_tool
            )
        )
        
        # Knowledge retrieval tools
        self.register(
            ToolDefinition(
                name="search_documents",
                description="Search across processed documents for relevant information",
                category=ToolCategory.KNOWLEDGE_RETRIEVAL,
                parameters=[
                    ToolParameter(
                        name="query",
                        type="string",
                        description="Search query",
                        required=True
                    ),
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to search (empty = all books)",
                        required=False,
                        default=[]
                    ),
                    ToolParameter(
                        name="top_k",
                        type="integer",
                        description="Number of results to return",
                        required=False,
                        default=5
                    )
                ],
                function=self._search_documents_tool
            )
        )
        
        # Content generation tools
        self.register(
            ToolDefinition(
                name="generate_questions",
                description="Generate questions from document content",
                category=ToolCategory.CONTENT_GENERATION,
                parameters=[
                    ToolParameter(
                        name="book_id",
                        type="string",
                        description="Book ID to generate questions from",
                        required=True
                    ),
                    ToolParameter(
                        name="question_type",
                        type="string",
                        description="Type of questions (10-mark, short-answer, etc.)",
                        required=False,
                        default="10-mark"
                    ),
                    ToolParameter(
                        name="num_questions",
                        type="integer",
                        description="Number of questions to generate",
                        required=False,
                        default=10
                    )
                ],
                function=self._generate_questions_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="answer_questions",
                description="Answer questions using document content",
                category=ToolCategory.CONTENT_GENERATION,
                parameters=[
                    ToolParameter(
                        name="questions",
                        type="list",
                        description="List of questions to answer",
                        required=True
                    ),
                    ToolParameter(
                        name="book_id",
                        type="string",
                        description="Book ID to use for answering",
                        required=True
                    ),
                    ToolParameter(
                        name="depth",
                        type="string",
                        description="Answer depth (short, medium, detailed)",
                        required=False,
                        default="detailed",
                        enum=["short", "medium", "detailed"]
                    )
                ],
                function=self._answer_questions_tool
            )
        )
        
        # Analysis tools
        self.register(
            ToolDefinition(
                name="analyze_topics",
                description="Analyze topics covered in documents",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to analyze",
                        required=True
                    ),
                    ToolParameter(
                        name="analysis_type",
                        type="string",
                        description="Type of analysis (topic_frequency, coverage, etc.)",
                        required=False,
                        default="topic_frequency"
                    )
                ],
                function=self._analyze_topics_tool
            )
        )
        
        # Export tools
        self.register(
            ToolDefinition(
                name="export_document",
                description="Export processed content to various formats",
                category=ToolCategory.EXPORT,
                parameters=[
                    ToolParameter(
                        name="book_id",
                        type="string",
                        description="Book ID to export",
                        required=True
                    ),
                    ToolParameter(
                        name="format",
                        type="string",
                        description="Export format",
                        required=False,
                        default="docx",
                        enum=["docx", "markdown", "pdf"]
                    ),
                    ToolParameter(
                        name="output_path",
                        type="string",
                        description="Output file path",
                        required=False,
                        default=""
                    )
                ],
                function=self._export_document_tool
            )
        )
        
        # Research-specific tools
        self.register(
            ToolDefinition(
                name="extract_citations",
                description="Extract and analyze citations and references from documents",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to analyze",
                        required=True
                    ),
                    ToolParameter(
                        name="citation_type",
                        type="string",
                        description="Type of citations to extract (academic, regulatory, clinical, all)",
                        required=False,
                        default="all"
                    )
                ],
                function=self._extract_citations_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="cross_reference",
                description="Find cross-references and connections between documents",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to cross-reference",
                        required=True
                    ),
                    ToolParameter(
                        name="reference_type",
                        type="string",
                        description="Type of references to find (conceptual, temporal, methodological, all)",
                        required=False,
                        default="all"
                    )
                ],
                function=self._cross_reference_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="extract_concepts",
                description="Extract key concepts, entities, and terminology from documents",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to analyze",
                        required=True
                    ),
                    ToolParameter(
                        name="concept_type",
                        type="string",
                        description="Type of concepts (technical, domain_specific, general, all)",
                        required=False,
                        default="all"
                    )
                ],
                function=self._extract_concepts_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="compare_documents",
                description="Compare multiple documents on specific aspects",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to compare",
                        required=True
                    ),
                    ToolParameter(
                        name="comparison_aspects",
                        type="list",
                        description="Aspects to compare (arguments, methodology, conclusions)",
                        required=False,
                        default=["all"]
                    )
                ],
                function=self._compare_documents_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="analyze_arguments",
                description="Analyze arguments, reasoning, and logic in documents",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to analyze",
                        required=True
                    ),
                    ToolParameter(
                        name="argument_type",
                        type="string",
                        description="Type of arguments (logical, persuasive, scientific, all)",
                        required=False,
                        default="all"
                    )
                ],
                function=self._analyze_arguments_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="create_timeline",
                description="Extract temporal information and create chronological timelines",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to analyze",
                        required=True
                    ),
                    ToolParameter(
                        name="timeline_type",
                        type="string",
                        description="Type of timeline (historical, procedural, developmental, all)",
                        required=False,
                        default="all"
                    )
                ],
                function=self._create_timeline_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="literature_review",
                description="Conduct literature review across documents",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to review",
                        required=True
                    ),
                    ToolParameter(
                        name="research_question",
                        type="string",
                        description="Research question to guide review",
                        required=True
                    ),
                    ToolParameter(
                        name="review_depth",
                        type="string",
                        description="Depth of review (comprehensive, focused, summary)",
                        required=False,
                        default="comprehensive"
                    )
                ],
                function=self._literature_review_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="extract_evidence",
                description="Extract evidence supporting specific claims",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to search",
                        required=True
                    ),
                    ToolParameter(
                        name="claim",
                        type="string",
                        description="Claim to find evidence for",
                        required=True
                    ),
                    ToolParameter(
                        name="evidence_type",
                        type="string",
                        description="Type of evidence (supporting, opposing, all)",
                        required=False,
                        default="all"
                    )
                ],
                function=self._extract_evidence_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="synthesize_findings",
                description="Synthesize findings from multiple sources",
                category=ToolCategory.CONTENT_GENERATION,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to synthesize",
                        required=True
                    ),
                    ToolParameter(
                        name="synthesis_type",
                        type="string",
                        description="Type of synthesis (integrative, comparative, critical)",
                        required=False,
                        default="integrative"
                    ),
                    ToolParameter(
                        name="focus_topic",
                        type="string",
                        description="Topic to focus synthesis on",
                        required=False,
                        default=""
                    )
                ],
                function=self._synthesize_findings_tool
            )
        )
        
        # Intelligent general ask tool
        self.register(
            ToolDefinition(
                name="general_ask",
                description="Intelligent research assistant - retrieves, explains, and synthesizes information with dynamic planning and gap resolution",
                category=ToolCategory.KNOWLEDGE_RETRIEVAL,
                parameters=[
                    ToolParameter(
                        name="query",
                        type="string",
                        description="User's question or request",
                        required=True
                    ),
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="Specific book IDs to use (empty = auto-select from all available)",
                        required=False,
                        default=[]
                    ),
                    ToolParameter(
                        name="excluded_book_ids",
                        type="list",
                        description="Book IDs to exclude from search",
                        required=False,
                        default=[]
                    ),
                    ToolParameter(
                        name="depth",
                        type="string",
                        description="Explanation depth (quick, standard, comprehensive)",
                        required=False,
                        default="standard",
                        enum=["quick", "standard", "comprehensive"]
                    ),
                    ToolParameter(
                        name="audience",
                        type="string",
                        description="Target audience level (beginner, intermediate, expert)",
                        required=False,
                        default="intermediate",
                        enum=["beginner", "intermediate", "expert"]
                    ),
                    ToolParameter(
                        name="include_citations",
                        type="boolean",
                        description="Include source citations in response",
                        required=False,
                        default=True
                    ),
                    ToolParameter(
                        name="auto_expand",
                        type="boolean",
                        description="Automatically expand search if initial results insufficient",
                        required=False,
                        default=True
                    )
                ],
                function=self._general_ask_tool
            )
        )
        
        # Data extraction tools
        self.register(
            ToolDefinition(
                name="extract_statistics",
                description="Extract numerical data, statistics, measurements, and quantitative information",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to analyze",
                        required=True
                    ),
                    ToolParameter(
                        name="stat_type",
                        type="string",
                        description="Type of statistics (descriptive, inferential, all)",
                        required=False,
                        default="all"
                    )
                ],
                function=self._extract_statistics_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="extract_tables_data",
                description="Extract and analyze tabular data, charts, and structured information",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to analyze",
                        required=True
                    ),
                    ToolParameter(
                        name="table_format",
                        type="string",
                        description="Output format for table data (structured, summary, raw)",
                        required=False,
                        default="structured"
                    )
                ],
                function=self._extract_tables_data_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="extract_methodology",
                description="Extract research methods, procedures, and methodological approaches",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to analyze",
                        required=True
                    ),
                    ToolParameter(
                        name="method_domain",
                        type="string",
                        description="Domain of methodology (scientific, clinical, engineering, all)",
                        required=False,
                        default="all"
                    )
                ],
                function=self._extract_methodology_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="extract_definitions",
                description="Extract formal definitions, terminology, and glossary terms",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to analyze",
                        required=True
                    ),
                    ToolParameter(
                        name="definition_type",
                        type="string",
                        description="Type of definitions (technical, domain_specific, all)",
                        required=False,
                        default="all"
                    )
                ],
                function=self._extract_definitions_tool
            )
        )
        
        # Advanced analysis tools
        self.register(
            ToolDefinition(
                name="sentiment_analysis",
                description="Analyze sentiment, opinions, and emotional tone in documents",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to analyze",
                        required=True
                    ),
                    ToolParameter(
                        name="sentiment_type",
                        type="string",
                        description="Type of sentiment analysis (overall, aspect_based, emotional)",
                        required=False,
                        default="overall"
                    )
                ],
                function=self._sentiment_analysis_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="trend_analysis",
                description="Identify trends, patterns, and changes over time or across documents",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to analyze",
                        required=True
                    ),
                    ToolParameter(
                        name="trend_type",
                        type="string",
                        description="Type of trend analysis (temporal, conceptual, frequency)",
                        required=False,
                        default="temporal"
                    )
                ],
                function=self._trend_analysis_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="correlation_analysis",
                description="Find correlations and relationships between concepts or variables",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to analyze",
                        required=True
                    ),
                    ToolParameter(
                        name="correlation_type",
                        type="string",
                        description="Type of correlation (statistical, conceptual, causal)",
                        required=False,
                        default="conceptual"
                    )
                ],
                function=self._correlation_analysis_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="clustering_analysis",
                description="Group similar concepts, documents, or themes into clusters",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to analyze",
                        required=True
                    ),
                    ToolParameter(
                        name="cluster_type",
                        type="string",
                        description="Type of clustering (thematic, conceptual, document)",
                        required=False,
                        default="thematic"
                    )
                ],
                function=self._clustering_analysis_tool
            )
        )
        
        # Validation tools
        self.register(
            ToolDefinition(
                name="fact_check",
                description="Verify claims and statements against document sources",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="claims",
                        type="list",
                        description="List of claims to verify",
                        required=True
                    ),
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to use for verification",
                        required=True
                    ),
                    ToolParameter(
                        name="strictness",
                        type="string",
                        description="Verification strictness (lenient, standard, strict)",
                        required=False,
                        default="standard"
                    )
                ],
                function=self._fact_check_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="consistency_check",
                description="Check for contradictions and inconsistencies across documents",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to analyze",
                        required=True
                    ),
                    ToolParameter(
                        name="check_type",
                        type="string",
                        description="Type of consistency check (factual, temporal, logical)",
                        required=False,
                        default="factual"
                    )
                ],
                function=self._consistency_check_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="completeness_check",
                description="Assess if information coverage is comprehensive and complete",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to analyze",
                        required=True
                    ),
                    ToolParameter(
                        name="topic",
                        type="string",
                        description="Topic to assess completeness for",
                        required=True
                    ),
                    ToolParameter(
                        name="completeness_criteria",
                        type="string",
                        description="Criteria for completeness (essential, comprehensive, exhaustive)",
                        required=False,
                        default="comprehensive"
                    )
                ],
                function=self._completeness_check_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="quality_assessment",
                description="Evaluate source quality, reliability, and credibility",
                category=ToolCategory.ANALYSIS,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to assess",
                        required=True
                    ),
                    ToolParameter(
                        name="quality_metrics",
                        type="list",
                        description="Quality metrics to evaluate (reliability, currency, authority, accuracy)",
                        required=False,
                        default=["all"]
                    )
                ],
                function=self._quality_assessment_tool
            )
        )
        
        # Synthesis tools
        self.register(
            ToolDefinition(
                name="summarize",
                description="Generate summaries of documents at different lengths and detail levels",
                category=ToolCategory.CONTENT_GENERATION,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to summarize",
                        required=True
                    ),
                    ToolParameter(
                        name="summary_length",
                        type="string",
                        description="Summary length (brief, standard, detailed)",
                        required=False,
                        default="standard"
                    ),
                    ToolParameter(
                        name="focus",
                        type="string",
                        description="Focus area for summary (optional)",
                        required=False,
                        default=""
                    )
                ],
                function=self._summarize_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="abstract_generation",
                description="Create abstracts for documents or research papers",
                category=ToolCategory.CONTENT_GENERATION,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to create abstracts for",
                        required=True
                    ),
                    ToolParameter(
                        name="abstract_type",
                        type="string",
                        description="Type of abstract (informative, descriptive, structured)",
                        required=False,
                        default="informative"
                    )
                ],
                function=self._abstract_generation_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="key_insights",
                description="Extract key insights, takeaways, and main points from documents",
                category=ToolCategory.CONTENT_GENERATION,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to analyze",
                        required=True
                    ),
                    ToolParameter(
                        name="insight_type",
                        type="string",
                        description="Type of insights (strategic, technical, practical)",
                        required=False,
                        default="all"
                    )
                ],
                function=self._key_insights_tool
            )
        )
        
        self.register(
            ToolDefinition(
                name="recommendation_generation",
                description="Generate recommendations based on document analysis",
                category=ToolCategory.CONTENT_GENERATION,
                parameters=[
                    ToolParameter(
                        name="book_ids",
                        type="list",
                        description="List of book IDs to base recommendations on",
                        required=True
                    ),
                    ToolParameter(
                        name="recommendation_type",
                        type="string",
                        description="Type of recommendations (actionable, strategic, research)",
                        required=False,
                        default="actionable"
                    ),
                    ToolParameter(
                        name="context",
                        type="string",
                        description="Context for recommendations (optional)",
                        required=False,
                        default=""
                    )
                ],
                function=self._recommendation_generation_tool
            )
        )
    
    def register(self, tool: ToolDefinition):
        """Register a tool in the registry."""
        self._tools[tool.name] = tool
    
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def list_tools(self, category: Optional[ToolCategory] = None) -> List[ToolDefinition]:
        """List all tools, optionally filtered by category."""
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools
    
    def get_tool_schema(self) -> List[Dict[str, Any]]:
        """Get tool schemas for LLM function calling."""
        schemas = []
        for tool in self._tools.values():
            schema = {
                "name": tool.name,
                "description": tool.description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
            
            for param in tool.parameters:
                schema["parameters"]["properties"][param.name] = {
                    "type": param.type,
                    "description": param.description
                }
                if param.enum:
                    schema["parameters"]["properties"][param.name]["enum"] = param.enum
                if param.default is not None:
                    schema["parameters"]["properties"][param.name]["default"] = param.default
                if param.required:
                    schema["parameters"]["required"].append(param.name)
            
            schemas.append(schema)
        
        return schemas
    
    # Tool implementations (connect to actual pipeline)
    def _process_pdf_tool(self, **kwargs) -> Dict[str, Any]:
        """Process PDF through pipeline."""
        try:
            # Import the actual pipeline function
            from src.modules.scripts.pipeline_signal_sections import run_signal_sections_pipeline
            
            pdf_path = kwargs.get("pdf_path")
            user_instruction = kwargs.get("user_instruction", "create comprehensive notes")
            ingestion_profile = kwargs.get("ingestion_profile", "fast_local")
            
            if not pdf_path or not os.path.exists(pdf_path):
                return {
                    "status": "error",
                    "error": "PDF file not found",
                    "book_id": None
                }
            
            # Call the actual pipeline
            result = run_signal_sections_pipeline(
                pdf_path=pdf_path,
                user_instruction=user_instruction
            )
            
            if result and result.get("book_id"):
                return {
                    "status": "success",
                    "book_id": result["book_id"],
                    "message": f"PDF processed successfully: {os.path.basename(pdf_path)}",
                    "instruction": user_instruction,
                    "pipeline_result": result
                }
            else:
                return {
                    "status": "error",
                    "error": "Pipeline processing failed",
                    "book_id": None
                }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "book_id": None
            }
    
    def _search_documents_tool(self, **kwargs) -> Dict[str, Any]:
        """Search documents using RAG."""
        try:
            from src.modules.storage.knowledge_store import KnowledgeStore
            from src.modules.rag.service import RagService
            
            query = kwargs.get("query")
            book_ids = kwargs.get("book_ids", [])
            top_k = kwargs.get("top_k", 5)
            
            # Use actual RAG service
            rag_service = RagService()
            
            if book_ids:
                # Search specific books
                results = []
                for book_id in book_ids:
                    book_results = rag_service.search(query, book_id=book_id, top_k=top_k)
                    results.extend(book_results)
            else:
                # Search all available books
                results = rag_service.search(query, top_k=top_k)
            
            return {
                "status": "success",
                "results": results[:top_k],
                "query": query,
                "num_results": len(results[:top_k])
            }
        except Exception as e:
            # Fallback to mock results if RAG not available
            return {
                "status": "error",
                "error": str(e),
                "results": [],
                "query": query
            }
    
    def _generate_questions_tool(self, **kwargs) -> Dict[str, Any]:
        """Generate questions from document."""
        try:
            from src.modules.interaction.ask_handler import AskHandler
            from src.modules.interaction.command_parser import IntentResult
            
            book_id = kwargs.get("book_id")
            question_type = kwargs.get("question_type", "10-mark")
            num_questions = kwargs.get("num_questions", 10)
            
            # Use actual question generation via AskHandler
            handler = AskHandler(
                book_id=book_id,
                book_title="Document",
                subject_hint="General",
                log_dir=None
            )
            
            # Create intent for question generation
            intent = IntentResult(
                task_type="generate_questions",
                scope="full_book",
                depth="medium",
                language_level="standard",
                format_type="paragraph"
            )
            
            result = handler.generate_questions(intent, num_questions=num_questions)
            
            return {
                "status": "success",
                "questions": result.get("questions", []),
                "book_id": book_id,
                "num_questions": len(result.get("questions", []))
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "questions": [],
                "book_id": book_id
            }
    
    def _answer_questions_tool(self, **kwargs) -> Dict[str, Any]:
        """Answer questions using document content."""
        try:
            from src.modules.generation.qa_engine import BookQaEngine
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            questions = kwargs.get("questions", [])
            book_id = kwargs.get("book_id")
            depth = kwargs.get("depth", "detailed")
            
            # Use actual QA engine
            knowledge_store = KnowledgeStore()
            book_title = knowledge_store.get_book_title(book_id)
            subject_hint = knowledge_store.get_book_subject(book_id)
            
            qa_engine = BookQaEngine(
                book_id=book_id,
                book_title=book_title or "Unknown",
                subject_hint=subject_hint or "General"
            )
            
            answers = {}
            for question in questions:
                result = qa_engine.answer(
                    question=question,
                    depth=depth,
                    language_level="standard",
                    format_type="paragraph"
                )
                answers[question] = result.get("answer", "No answer generated")
            
            return {
                "status": "success",
                "answers": answers,
                "book_id": book_id,
                "num_questions": len(questions)
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "answers": {},
                "book_id": book_id
            }
    
    def _analyze_topics_tool(self, **kwargs) -> Dict[str, Any]:
        """Analyze topics in documents."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            analysis_type = kwargs.get("analysis_type", "topic_frequency")
            
            router = RewriteModelRouter()
            topic_analyses = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to analyze topics
                system_prompt = "You are a topic analysis specialist. Analyze topics covered in documents."
                user_prompt = f"Perform {analysis_type} topic analysis on the following text. Identify main topics, subtopics, and their relationships.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                topic_analyses.append({
                    "book_id": book_id,
                    "topic_analysis": result.get("text", ""),
                    "analysis_type": analysis_type
                })
            
            return {
                "status": "success",
                "topic_analyses": topic_analyses,
                "analysis_type": analysis_type,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "topic_analyses": [],
                "book_ids": book_ids
            }
    
    def _export_document_tool(self, **kwargs) -> Dict[str, Any]:
        """Export document to format."""
        try:
            from src.modules.storage.knowledge_store import KnowledgeStore
            import os
            from datetime import datetime
            
            book_id = kwargs.get("book_id")
            format_type = kwargs.get("format", "docx")
            output_path = kwargs.get("output_path", "")
            
            knowledge_store = KnowledgeStore()
            
            # Get document content
            content = knowledge_store.get_book_content(book_id)
            if not content:
                return {
                    "status": "error",
                    "error": "Book content not found",
                    "output_path": output_path,
                    "book_id": book_id
                }
            
            # Generate output path if not provided
            if not output_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = f"export_{book_id}_{timestamp}.{format_type}"
            
            # Perform export based on format
            if format_type == "markdown":
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            elif format_type == "docx":
                # For docx, we'd need a proper docx library
                # For now, save as markdown with .docx extension
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            elif format_type == "pdf":
                # For PDF, we'd need a PDF generation library
                # For now, save as markdown with .pdf extension
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            return {
                "status": "success",
                "output_path": os.path.abspath(output_path),
                "book_id": book_id,
                "format": format_type
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "output_path": output_path,
                "book_id": book_id
            }
    
    # Research tool implementations
    def _extract_citations_tool(self, **kwargs) -> Dict[str, Any]:
        """Extract and analyze citations from documents."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            citation_type = kwargs.get("citation_type", "all")
            
            router = RewriteModelRouter()
            citations = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to extract citations
                system_prompt = "You are a citation extraction specialist. Extract and analyze citations and references from documents."
                user_prompt = f"Extract all {citation_type} citations and references from the following text. Identify source types, authors, dates, and key information.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                citations.append({
                    "book_id": book_id,
                    "extracted_citations": result.get("text", ""),
                    "citation_type": citation_type
                })
            
            return {
                "status": "success",
                "citations": citations,
                "citation_type": citation_type,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "citations": [],
                "book_ids": book_ids
            }
    
    def _cross_reference_tool(self, **kwargs) -> Dict[str, Any]:
        """Find cross-references between documents."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            reference_type = kwargs.get("reference_type", "all")
            
            router = RewriteModelRouter()
            cross_references = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to find cross-references
                system_prompt = "You are a cross-reference analysis specialist. Find cross-references and connections between documents."
                user_prompt = f"Find all {reference_type} cross-references and connections in the following text. Identify related concepts, themes, and references.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                cross_references.append({
                    "book_id": book_id,
                    "cross_references": result.get("text", ""),
                    "reference_type": reference_type
                })
            
            return {
                "status": "success",
                "cross_references": cross_references,
                "reference_type": reference_type,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "cross_references": [],
                "book_ids": book_ids
            }
    
    def _extract_concepts_tool(self, **kwargs) -> Dict[str, Any]:
        """Extract key concepts and entities from documents."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            concept_type = kwargs.get("concept_type", "all")
            
            router = RewriteModelRouter()
            concepts = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to extract concepts
                system_prompt = "You are a concept extraction specialist. Extract key concepts, entities, and terminology from documents."
                user_prompt = f"Extract all {concept_type} key concepts, entities, and terminology from the following text. Organize them by importance and relationships.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                concepts.append({
                    "book_id": book_id,
                    "extracted_concepts": result.get("text", ""),
                    "concept_type": concept_type
                })
            
            return {
                "status": "success",
                "concepts": concepts,
                "concept_type": concept_type,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "concepts": [],
                "book_ids": book_ids
            }
    
    def _compare_documents_tool(self, **kwargs) -> Dict[str, Any]:
        """Compare multiple documents on specific aspects."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            comparison_aspects = kwargs.get("comparison_aspects", ["all"])
            
            router = RewriteModelRouter()
            comparisons = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to compare documents
                system_prompt = "You are a document comparison specialist. Compare multiple documents on specific aspects."
                user_prompt = f"Compare this document on the following aspects: {', '.join(comparison_aspects)}. Identify similarities, differences, and key comparative points.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                comparisons.append({
                    "book_id": book_id,
                    "comparison": result.get("text", ""),
                    "aspects": comparison_aspects
                })
            
            return {
                "status": "success",
                "comparisons": comparisons,
                "aspects": comparison_aspects,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "comparisons": [],
                "book_ids": book_ids
            }
    
    def _analyze_arguments_tool(self, **kwargs) -> Dict[str, Any]:
        """Analyze arguments and reasoning in documents."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            argument_type = kwargs.get("argument_type", "all")
            
            router = RewriteModelRouter()
            arguments = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to analyze arguments
                system_prompt = "You are an argument analysis specialist. Analyze arguments, reasoning, and logic in documents."
                user_prompt = f"Analyze the {argument_type} arguments and reasoning in the following text. Identify main arguments, logical structure, and reasoning patterns.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                arguments.append({
                    "book_id": book_id,
                    "argument_analysis": result.get("text", ""),
                    "argument_type": argument_type
                })
            
            return {
                "status": "success",
                "arguments": arguments,
                "argument_type": argument_type,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "arguments": [],
                "book_ids": book_ids
            }
    
    def _create_timeline_tool(self, **kwargs) -> Dict[str, Any]:
        """Extract temporal information and create timeline."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            timeline_type = kwargs.get("timeline_type", "all")
            
            router = RewriteModelRouter()
            timelines = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to create timeline
                system_prompt = "You are a timeline analysis specialist. Extract temporal information and create chronological timelines."
                user_prompt = f"Extract temporal information and create a {timeline_type} timeline from the following text. Identify key dates, events, and chronological sequences.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                timelines.append({
                    "book_id": book_id,
                    "timeline": result.get("text", ""),
                    "timeline_type": timeline_type
                })
            
            return {
                "status": "success",
                "timelines": timelines,
                "timeline_type": timeline_type,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timelines": [],
                "book_ids": book_ids
            }
    
    def _literature_review_tool(self, **kwargs) -> Dict[str, Any]:
        """Conduct literature review across documents."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            research_question = kwargs.get("research_question", "")
            review_depth = kwargs.get("review_depth", "comprehensive")
            
            router = RewriteModelRouter()
            literature_reviews = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to conduct literature review
                system_prompt = "You are a literature review specialist. Conduct literature reviews across documents."
                user_prompt = f"Conduct a {review_depth} literature review of the following document. Research question: {research_question}. Identify key themes, findings, and research gaps.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                literature_reviews.append({
                    "book_id": book_id,
                    "literature_review": result.get("text", ""),
                    "research_question": research_question,
                    "review_depth": review_depth
                })
            
            return {
                "status": "success",
                "literature_reviews": literature_reviews,
                "research_question": research_question,
                "review_depth": review_depth,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "literature_reviews": [],
                "book_ids": book_ids
            }
    
    def _extract_evidence_tool(self, **kwargs) -> Dict[str, Any]:
        """Extract evidence supporting specific claims."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            from src.modules.rag.service import RagService
            
            book_ids = kwargs.get("book_ids", [])
            claim = kwargs.get("claim", "")
            evidence_type = kwargs.get("evidence_type", "all")
            
            router = RewriteModelRouter()
            rag_service = RagService()
            evidence_results = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Search for evidence
                search_results = rag_service.search(claim, book_id=book_id, top_k=3)
                evidence_text = "\n".join([r.get("text", "") for r in search_results[:5]])
                
                # Use LLM to extract evidence
                system_prompt = "You are an evidence extraction specialist. Extract evidence supporting specific claims."
                user_prompt = f"Extract {evidence_type} evidence from the following text that supports or opposes this claim: {claim}.\n\nEvidence context: {evidence_text}\n\nDocument content: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1000
                )
                
                evidence_results.append({
                    "book_id": book_id,
                    "evidence": result.get("text", ""),
                    "claim": claim,
                    "evidence_type": evidence_type
                })
            
            return {
                "status": "success",
                "evidence": evidence_results,
                "evidence_type": evidence_type,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "evidence": [],
                "book_ids": book_ids
            }
    
    def _synthesize_findings_tool(self, **kwargs) -> Dict[str, Any]:
        """Synthesize findings from multiple sources."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            synthesis_type = kwargs.get("synthesis_type", "integrative")
            focus_topic = kwargs.get("focus_topic", "")
            
            router = RewriteModelRouter()
            syntheses = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to synthesize findings
                system_prompt = "You are a synthesis specialist. Synthesize findings from multiple sources."
                focus_prompt = f"Focus on the topic: {focus_topic}\n\n" if focus_topic else ""
                user_prompt = f"{focus_prompt}Perform a {synthesis_type} synthesis of the following text. Integrate key findings and identify patterns.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                syntheses.append({
                    "book_id": book_id,
                    "synthesis": result.get("text", ""),
                    "synthesis_type": synthesis_type,
                    "focus_topic": focus_topic
                })
            
            return {
                "status": "success",
                "syntheses": syntheses,
                "synthesis_type": synthesis_type,
                "focus_topic": focus_topic,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "syntheses": [],
                "book_ids": book_ids
            }
    
    def _general_ask_tool(self, **kwargs) -> Dict[str, Any]:
        """Intelligent research assistant with dynamic planning and gap resolution."""
        query = kwargs.get("query", "")
        book_ids = kwargs.get("book_ids", [])
        excluded_book_ids = kwargs.get("excluded_book_ids", [])
        depth = kwargs.get("depth", "standard")
        audience = kwargs.get("audience", "intermediate")
        include_citations = kwargs.get("include_citations", True)
        auto_expand = kwargs.get("auto_expand", True)
        
        # Dynamic planning: analyze query complexity and needed steps
        analysis_result = self._analyze_query_complexity(query)
        
        # Document selection
        selected_books = self._select_documents(book_ids, excluded_book_ids, analysis_result)
        
        # Initial retrieval
        initial_results = self._perform_retrieval(query, selected_books, depth)
        
        # Gap detection and resolution
        gaps = self._detect_information_gaps(initial_results, query, analysis_result)
        
        if gaps and auto_expand:
            expanded_results = self._resolve_gaps(gaps, selected_books, query)
            final_results = self._merge_results(initial_results, expanded_results)
        else:
            final_results = initial_results
        
        # Generate explanation
        explanation = self._generate_explanation(
            query, final_results, depth, audience, include_citations
        )
        
        return {
            "status": "success",
            "query": query,
            "answer": explanation,
            "books_used": selected_books,
            "gaps_detected": gaps,
            "gaps_resolved": len(gaps) if auto_expand else 0,
            "complexity_analysis": analysis_result,
            "depth": depth,
            "audience": audience
        }
    
    def _analyze_query_complexity(self, query: str) -> Dict[str, Any]:
        """Analyze query complexity and determine needed approach."""
        # Simple heuristic analysis
        complexity_indicators = {
            "multi_part": any(word in query.lower() for word in ["and", "also", "additionally", "furthermore"]),
            "comparative": any(word in query.lower() for word in ["compare", "difference", "versus", "vs"]),
            "causal": any(word in query.lower() for word in ["why", "because", "cause", "effect"]),
            "temporal": any(word in query.lower() for word in ["when", "timeline", "history", "evolution"]),
            "technical": len(query.split()) > 15  # Longer queries tend to be more technical
        }
        
        complexity_score = sum(complexity_indicators.values())
        
        return {
            "complexity_score": complexity_score,
            "indicators": complexity_indicators,
            "requires_multi_step": complexity_score >= 2,
            "suggested_approach": "comprehensive" if complexity_score >= 3 else "standard"
        }
    
    def _select_documents(self, book_ids: List[str], excluded_book_ids: List[str], analysis: Dict[str, Any]) -> List[str]:
        """Select appropriate documents based on user preferences and analysis."""
        from src.modules.agent.state_manager import get_state_manager
        
        state_manager = get_state_manager()
        all_documents = state_manager.get_processed_documents()
        
        available_book_ids = [doc.book_id for doc in all_documents if doc.book_id]
        
        # User specified specific books
        if book_ids:
            selected = [bid for bid in book_ids if bid in available_book_ids]
        else:
            # Auto-select based on analysis
            if analysis.get("requires_multi_step"):
                # For complex queries, use all available documents
                selected = available_book_ids
            else:
                # For simple queries, use most recent documents
                selected = available_book_ids[:3] if len(available_book_ids) > 3 else available_book_ids
        
        # Apply exclusions
        selected = [bid for bid in selected if bid not in excluded_book_ids]
        
        return selected
    
    def _perform_retrieval(self, query: str, book_ids: List[str], depth: str) -> Dict[str, Any]:
        """Perform initial information retrieval."""
        try:
            from src.modules.rag.service import RagService
            
            rag_service = RagService()
            retrieval_depth = {
                "quick": 3,
                "standard": 5,
                "comprehensive": 10
            }.get(depth, 5)
            
            if book_ids:
                results = []
                for book_id in book_ids:
                    book_results = rag_service.search(query, book_id=book_id, top_k=retrieval_depth)
                    results.extend(book_results)
            else:
                results = rag_service.search(query, top_k=retrieval_depth)
            
            return {
                "results": results[:retrieval_depth],
                "num_results": len(results[:retrieval_depth]),
                "query": query,
                "book_ids_used": book_ids
            }
        except Exception as e:
            return {
                "results": [],
                "num_results": 0,
                "query": query,
                "book_ids_used": book_ids,
                "error": str(e)
            }
    
    def _detect_information_gaps(self, results: Dict[str, Any], query: str, analysis: Dict[str, Any]) -> List[str]:
        """Detect gaps in retrieved information."""
        gaps = []
        
        # Check if we have enough results
        if results.get("num_results", 0) < 3:
            gaps.append("insufficient_retrieval_results")
        
        # Check for complexity-specific gaps
        if analysis.get("indicators", {}).get("comparative"):
            gaps.append("comparative_analysis_needed")
        
        if analysis.get("indicators", {}).get("temporal"):
            gaps.append("temporal_context_needed")
        
        return gaps
    
    def _resolve_gaps(self, gaps: List[str], book_ids: List[str], query: str) -> Dict[str, Any]:
        """Resolve detected information gaps through expanded search."""
        expanded_results = {}
        
        for gap in gaps:
            if gap == "insufficient_retrieval_results":
                # Expand search to more documents
                expanded_results["expanded_retrieval"] = self._perform_retrieval(query, book_ids, "comprehensive")
            elif gap == "comparative_analysis_needed":
                # Add comparative analysis
                expanded_results["comparative_analysis"] = self._perform_comparative_analysis(book_ids, query)
            elif gap == "temporal_context_needed":
                # Add temporal information
                expanded_results["temporal_context"] = self._perform_temporal_analysis(book_ids, query)
        
        return expanded_results
    
    def _merge_results(self, initial: Dict[str, Any], expanded: Dict[str, Any]) -> Dict[str, Any]:
        """Merge initial and expanded results."""
        merged = initial.copy()
        merged["expanded_results"] = expanded
        return merged
    
    def _generate_explanation(self, query: str, results: Dict[str, Any], depth: str, audience: str, include_citations: bool) -> str:
        """Generate comprehensive explanation based on retrieved information."""
        # This would use the LLM to generate the actual explanation
        # For now, return a template response
        
        explanation_parts = [
            f"Based on the analysis of your query: '{query}'",
            f"\nDepth: {depth}, Audience: {audience}",
            f"\nInformation sources: {results.get('book_ids_used', [])}",
        ]
        
        if include_citations:
            explanation_parts.append("\nCitations would be included here.")
        
        if "expanded_results" in results:
            explanation_parts.append(f"\nAdditional context was added to address information gaps.")
        
        return "\n".join(explanation_parts)
    
    def _perform_comparative_analysis(self, book_ids: List[str], query: str) -> Dict[str, Any]:
        """Perform comparative analysis across documents."""
        return {"comparisons": [], "book_ids": book_ids}
    
    def _perform_temporal_analysis(self, book_ids: List[str], query: str) -> Dict[str, Any]:
        """Perform temporal analysis."""
        return {"timeline": [], "book_ids": book_ids}
    
    # Data extraction tool implementations
    def _extract_statistics_tool(self, **kwargs) -> Dict[str, Any]:
        """Extract numerical data and statistics."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            stat_type = kwargs.get("stat_type", "all")
            
            router = RewriteModelRouter()
            statistics = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to extract numerical data
                system_prompt = "You are a data extraction specialist. Extract numerical data, statistics, measurements, and quantitative information from the provided text."
                user_prompt = f"Extract all numerical data, statistics, measurements, and quantitative information from the following text. Return the results in a structured format.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=2000
                )
                
                statistics.append({
                    "book_id": book_id,
                    "extracted_data": result.get("text", ""),
                    "stat_type": stat_type
                })
            
            return {
                "status": "success",
                "statistics": statistics,
                "stat_type": stat_type,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "statistics": [],
                "book_ids": book_ids
            }
    
    def _extract_tables_data_tool(self, **kwargs) -> Dict[str, Any]:
        """Extract and analyze tabular data."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            table_format = kwargs.get("table_format", "structured")
            
            router = RewriteModelRouter()
            tables = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to extract tabular data
                system_prompt = "You are a data extraction specialist. Extract tabular data, charts, and structured information from the provided text."
                user_prompt = f"Extract all tabular data, charts, and structured information from the following text. Return the results in a {table_format} format.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=2000
                )
                
                tables.append({
                    "book_id": book_id,
                    "extracted_tables": result.get("text", ""),
                    "table_format": table_format
                })
            
            return {
                "status": "success",
                "tables": tables,
                "table_format": table_format,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "tables": [],
                "book_ids": book_ids
            }
    
    def _extract_methodology_tool(self, **kwargs) -> Dict[str, Any]:
        """Extract research methods and procedures."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            method_domain = kwargs.get("method_domain", "all")
            
            router = RewriteModelRouter()
            methodologies = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to extract methodology
                system_prompt = "You are a research methodology specialist. Extract research methods, procedures, and methodological approaches from the provided text."
                user_prompt = f"Extract all research methods, procedures, and methodological approaches from the following text, focusing on {method_domain} methods.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=2000
                )
                
                methodologies.append({
                    "book_id": book_id,
                    "extracted_methodologies": result.get("text", ""),
                    "method_domain": method_domain
                })
            
            return {
                "status": "success",
                "methodologies": methodologies,
                "method_domain": method_domain,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "methodologies": [],
                "book_ids": book_ids
            }
    
    def _extract_definitions_tool(self, **kwargs) -> Dict[str, Any]:
        """Extract formal definitions and terminology."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            definition_type = kwargs.get("definition_type", "all")
            
            router = RewriteModelRouter()
            definitions = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to extract definitions
                system_prompt = "You are a terminology specialist. Extract formal definitions, terminology, and glossary terms from the provided text."
                user_prompt = f"Extract all formal definitions, terminology, and glossary terms from the following text, focusing on {definition_type} definitions.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=2000
                )
                
                definitions.append({
                    "book_id": book_id,
                    "extracted_definitions": result.get("text", ""),
                    "definition_type": definition_type
                })
            
            return {
                "status": "success",
                "definitions": definitions,
                "definition_type": definition_type,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "definitions": [],
                "book_ids": book_ids
            }
    
    # Advanced analysis tool implementations
    def _sentiment_analysis_tool(self, **kwargs) -> Dict[str, Any]:
        """Analyze sentiment and opinions."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            sentiment_type = kwargs.get("sentiment_type", "overall")
            
            router = RewriteModelRouter()
            sentiment_results = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to analyze sentiment
                system_prompt = "You are a sentiment analysis specialist. Analyze sentiment, opinions, and emotional tone in the provided text."
                user_prompt = f"Perform {sentiment_type} sentiment analysis on the following text. Identify the overall sentiment, key emotional indicators, and opinion patterns.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                sentiment_results.append({
                    "book_id": book_id,
                    "sentiment_analysis": result.get("text", ""),
                    "sentiment_type": sentiment_type
                })
            
            return {
                "status": "success",
                "sentiment_results": sentiment_results,
                "sentiment_type": sentiment_type,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "sentiment_results": [],
                "book_ids": book_ids
            }
    
    def _trend_analysis_tool(self, **kwargs) -> Dict[str, Any]:
        """Identify trends and patterns."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            trend_type = kwargs.get("trend_type", "temporal")
            
            router = RewriteModelRouter()
            trends = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to identify trends
                system_prompt = "You are a trend analysis specialist. Identify trends, patterns, and changes over time or across documents in the provided text."
                user_prompt = f"Perform {trend_type} trend analysis on the following text. Identify key trends, patterns, and changes.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                trends.append({
                    "book_id": book_id,
                    "trend_analysis": result.get("text", ""),
                    "trend_type": trend_type
                })
            
            return {
                "status": "success",
                "trends": trends,
                "trend_type": trend_type,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "trends": [],
                "book_ids": book_ids
            }
    
    def _correlation_analysis_tool(self, **kwargs) -> Dict[str, Any]:
        """Find correlations between concepts."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            correlation_type = kwargs.get("correlation_type", "conceptual")
            
            router = RewriteModelRouter()
            correlations = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to find correlations
                system_prompt = "You are a correlation analysis specialist. Find correlations and relationships between concepts or variables in the provided text."
                user_prompt = f"Perform {correlation_type} correlation analysis on the following text. Identify key relationships and correlations.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                correlations.append({
                    "book_id": book_id,
                    "correlation_analysis": result.get("text", ""),
                    "correlation_type": correlation_type
                })
            
            return {
                "status": "success",
                "correlations": correlations,
                "correlation_type": correlation_type,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "correlations": [],
                "book_ids": book_ids
            }
    
    def _clustering_analysis_tool(self, **kwargs) -> Dict[str, Any]:
        """Group similar concepts into clusters."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            cluster_type = kwargs.get("cluster_type", "thematic")
            
            router = RewriteModelRouter()
            clusters = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to perform clustering
                system_prompt = "You are a clustering analysis specialist. Group similar concepts, documents, or themes into clusters in the provided text."
                user_prompt = f"Perform {cluster_type} clustering analysis on the following text. Identify and group similar concepts.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                clusters.append({
                    "book_id": book_id,
                    "clustering_analysis": result.get("text", ""),
                    "cluster_type": cluster_type
                })
            
            return {
                "status": "success",
                "clusters": clusters,
                "cluster_type": cluster_type,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "clusters": [],
                "book_ids": book_ids
            }
    
    # Validation tool implementations
    def _fact_check_tool(self, **kwargs) -> Dict[str, Any]:
        """Verify claims against sources."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            from src.modules.rag.service import RagService
            
            claims = kwargs.get("claims", [])
            book_ids = kwargs.get("book_ids", [])
            strictness = kwargs.get("strictness", "standard")
            
            router = RewriteModelRouter()
            rag_service = RagService()
            fact_checks = {}
            
            for claim in claims:
                # Search for evidence of the claim
                search_results = []
                for book_id in book_ids:
                    results = rag_service.search(claim, book_id=book_id, top_k=3)
                    search_results.extend(results)
                
                # Use LLM to verify claim against evidence
                evidence_text = "\n".join([r.get("text", "") for r in search_results[:5]])
                system_prompt = f"You are a fact-checking specialist with {strictness} strictness. Verify claims against provided evidence."
                user_prompt = f"Claim: {claim}\n\nEvidence from documents:\n{evidence_text}\n\nIs this claim supported by the evidence? Provide a fact-check assessment."
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1000
                )
                
                fact_checks[claim] = {
                    "verification": result.get("text", ""),
                    "evidence_count": len(search_results),
                    "strictness": strictness
                }
            
            return {
                "status": "success",
                "fact_checks": fact_checks,
                "strictness": strictness,
                "claims_checked": len(claims),
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "fact_checks": {},
                "book_ids": book_ids
            }
    
    def _consistency_check_tool(self, **kwargs) -> Dict[str, Any]:
        """Check for contradictions and inconsistencies."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            check_type = kwargs.get("check_type", "factual")
            
            router = RewriteModelRouter()
            inconsistencies = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to check for inconsistencies
                system_prompt = "You are a consistency analysis specialist. Check for contradictions and inconsistencies in the provided text."
                user_prompt = f"Perform {check_type} consistency check on the following text. Identify any contradictions, inconsistencies, or conflicting information.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                inconsistencies.append({
                    "book_id": book_id,
                    "consistency_analysis": result.get("text", ""),
                    "check_type": check_type
                })
            
            return {
                "status": "success",
                "inconsistencies": inconsistencies,
                "check_type": check_type,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "inconsistencies": [],
                "book_ids": book_ids
            }
    
    def _completeness_check_tool(self, **kwargs) -> Dict[str, Any]:
        """Assess information completeness."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            topic = kwargs.get("topic", "")
            completeness_criteria = kwargs.get("completeness_criteria", "comprehensive")
            
            router = RewriteModelRouter()
            completeness_assessments = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to assess completeness
                system_prompt = f"You are a completeness analysis specialist. Assess if information coverage is {completeness_criteria} for a given topic."
                user_prompt = f"Assess the completeness of coverage for the topic '{topic}' using {completeness_criteria} criteria. Identify missing aspects and gaps.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                completeness_assessments.append({
                    "book_id": book_id,
                    "completeness_assessment": result.get("text", ""),
                    "topic": topic,
                    "completeness_criteria": completeness_criteria
                })
            
            return {
                "status": "success",
                "completeness_assessments": completeness_assessments,
                "topic": topic,
                "completeness_criteria": completeness_criteria,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "completeness_assessments": [],
                "book_ids": book_ids
            }
    
    def _quality_assessment_tool(self, **kwargs) -> Dict[str, Any]:
        """Evaluate source quality and credibility."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            quality_metrics = kwargs.get("quality_metrics", ["all"])
            
            router = RewriteModelRouter()
            quality_assessments = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to assess quality
                system_prompt = "You are a quality assessment specialist. Evaluate source quality, reliability, and credibility."
                user_prompt = f"Evaluate the quality of this document using these metrics: {', '.join(quality_metrics)}. Assess reliability, currency, authority, and accuracy.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                quality_assessments.append({
                    "book_id": book_id,
                    "quality_assessment": result.get("text", ""),
                    "quality_metrics": quality_metrics
                })
            
            return {
                "status": "success",
                "quality_assessments": quality_assessments,
                "quality_metrics": quality_metrics,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "quality_assessments": [],
                "book_ids": book_ids
            }
    
    # Synthesis tool implementations
    def _summarize_tool(self, **kwargs) -> Dict[str, Any]:
        """Generate document summaries."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            summary_length = kwargs.get("summary_length", "standard")
            focus = kwargs.get("focus", "")
            
            router = RewriteModelRouter()
            summaries = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                # Get document content for summarization
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Determine max tokens based on summary length
                max_tokens = {
                    "brief": 500,
                    "standard": 1000,
                    "detailed": 2000
                }.get(summary_length, 1000)
                
                # Generate summary using LLM
                system_prompt = "You are a helpful assistant that creates clear, concise summaries."
                user_prompt = f"Summarize the following content. Focus: {focus if focus else 'main points'}\n\nContent: {content[:10000]}"  # Limit content length
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=max_tokens
                )
                
                summaries.append({
                    "book_id": book_id,
                    "summary": result.get("text", ""),
                    "summary_length": summary_length
                })
            
            return {
                "status": "success",
                "summaries": summaries,
                "summary_length": summary_length,
                "focus": focus,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "summaries": [],
                "book_ids": book_ids
            }
    
    def _abstract_generation_tool(self, **kwargs) -> Dict[str, Any]:
        """Create abstracts for documents."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            abstract_type = kwargs.get("abstract_type", "informative")
            
            router = RewriteModelRouter()
            abstracts = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to generate abstract
                system_prompt = "You are an abstract generation specialist. Create abstracts for documents or research papers."
                user_prompt = f"Create a {abstract_type} abstract for the following document. Include key objectives, methods, findings, and conclusions.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                abstracts.append({
                    "book_id": book_id,
                    "abstract": result.get("text", ""),
                    "abstract_type": abstract_type
                })
            
            return {
                "status": "success",
                "abstracts": abstracts,
                "abstract_type": abstract_type,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "abstracts": [],
                "book_ids": book_ids
            }
    
    def _key_insights_tool(self, **kwargs) -> Dict[str, Any]:
        """Extract key insights and takeaways."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            insight_type = kwargs.get("insight_type", "all")
            
            router = RewriteModelRouter()
            insights = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to extract key insights
                system_prompt = "You are an insight extraction specialist. Extract key insights, takeaways, and main points from documents."
                user_prompt = f"Extract key insights, takeaways, and main points from the following document, focusing on {insight_type} insights.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                insights.append({
                    "book_id": book_id,
                    "insights": result.get("text", ""),
                    "insight_type": insight_type
                })
            
            return {
                "status": "success",
                "insights": insights,
                "insight_type": insight_type,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "insights": [],
                "book_ids": book_ids
            }
    
    def _recommendation_generation_tool(self, **kwargs) -> Dict[str, Any]:
        """Generate recommendations based on analysis."""
        try:
            from src.modules.generation.rewrite import RewriteModelRouter
            from src.modules.storage.knowledge_store import KnowledgeStore
            
            book_ids = kwargs.get("book_ids", [])
            recommendation_type = kwargs.get("recommendation_type", "actionable")
            context = kwargs.get("context", "")
            
            router = RewriteModelRouter()
            recommendations = []
            
            for book_id in book_ids:
                knowledge_store = KnowledgeStore()
                content = knowledge_store.get_book_content(book_id)
                
                if not content:
                    continue
                
                # Use LLM to generate recommendations
                system_prompt = "You are a recommendation generation specialist. Generate recommendations based on document analysis."
                context_prompt = f"Context: {context}\n\n" if context else ""
                user_prompt = f"{context_prompt}Generate {recommendation_type} recommendations based on the analysis of this document.\n\nContent: {content[:15000]}"
                
                result = router.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1500
                )
                
                recommendations.append({
                    "book_id": book_id,
                    "recommendations": result.get("text", ""),
                    "recommendation_type": recommendation_type,
                    "context": context
                })
            
            return {
                "status": "success",
                "recommendations": recommendations,
                "recommendation_type": recommendation_type,
                "context": context,
                "book_ids": book_ids
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "recommendations": [],
                "book_ids": book_ids
            }


# Global registry instance
_tool_registry = None

def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry

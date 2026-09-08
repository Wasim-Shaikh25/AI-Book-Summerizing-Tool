# Grounded Generation Workflows

This document describes how the existing parametric tools compose to enable various grounded generation workflows without requiring new tools.

## Workflow: Questions + Answers Generation

**Goal:** Generate Q&A pairs from document corpus.

**Tool Composition:**
1. `extract_items(doc_id, item_schema, instruction)` - Extract questions from assessment documents or generate questions from content
2. `search_documents(query, book_ids)` - Retrieve relevant sections for answering each question
3. `generate_content(instruction, context_chunks)` - Generate answers with citations

**Example Agent Plan:**
```
1. extract_items: instruction="Extract all questions from this assessment document"
2. For each question:
   - search_documents: query=<question>
   - generate_content: instruction="Answer this question based on the retrieved context"
3. export_docx: Compile Q&A pairs into document
```

**Domains Supported:**
- Law: Extract questions from past exam papers, answer using case law
- Medicine: Extract clinical questions, answer using textbook content
- Engineering: Extract problem statements, answer using manual content
- Business: Extract case study questions, answer using report content

---

## Workflow: Evidence Tables

**Goal:** Create structured evidence tables comparing sources on specific dimensions.

**Tool Composition:**
1. `compare_documents(doc_ids, aspect, instruction)` - Built-in evidence diff
2. `extract_items(doc_id, item_schema, instruction)` - Extract specific data points
3. `generate_content(instruction, context_chunks)` - Format as table

**Example Agent Plan:**
```
1. compare_documents: aspect="treatment efficacy", instruction="Create comparison table"
2. generate_content: instruction="Format evidence as markdown table with columns: Source, Evidence, Strength"
3. export_markdown: Save as .md file
```

**Domains Supported:**
- Medicine: Drug efficacy comparison across clinical guidelines
- Law: Case law comparison on legal principles
- Engineering: Specification comparison across standards
- Business: Financial metric comparison across reports

---

## Workflow: Concept Maps

**Goal:** Generate visual concept maps showing relationships between topics.

**Tool Composition:**
1. `traverse_concepts(concept_name, max_hops)` - Use knowledge graph to find related concepts
2. `generate_content(instruction, context_chunks)` - Generate Mermaid diagram syntax
3. `export_markdown` - Save diagram in markdown

**Example Agent Plan:**
```
1. traverse_concepts: concept_name="photosynthesis", max_hops=3
2. generate_content: instruction="Generate Mermaid flowchart syntax showing relationships between these concepts"
3. export_markdown: Save as .md with Mermaid diagram
```

**Domains Supported:**
- Biology: Metabolic pathways
- Law: Legal concept relationships
- Engineering: Process flows
- Business: Organizational structures

---

## Workflow: Timelines

**Goal:** Create chronological timelines of events or developments.

**Tool Composition:**
1. `extract_items(doc_id, item_schema, instruction)` - Extract dates and events
2. `analyze_corpus_trends(extracted_items, analysis_type)` - Sort and analyze chronologically
3. `generate_content(instruction, context_chunks)` - Format as timeline
4. `export_markdown` - Save as markdown

**Example Agent Plan:**
```
1. extract_items: instruction="Extract all dates and associated events"
2. analyze_corpus_trends: analysis_type="patterns" to identify chronological patterns
3. generate_content: instruction="Format as chronological timeline with years and events"
4. export_markdown: Save timeline
```

**Domains Supported:**
- History: Historical event timelines
- Law: Case law development over time
- Medicine: Medical discovery timeline
- Business: Company milestone timeline

---

## Workflow: Study Guides

**Goal:** Generate comprehensive study guides from multiple sources.

**Tool Composition:**
1. `map_outline_to_corpus(outline_text, book_ids)` - Map syllabus to textbooks
2. For each covered topic:
   - `search_documents` - Retrieve content
   - `generate_content` - Summarize with key points
3. `export_docx` - Compile study guide

**Example Agent Plan:**
```
1. map_outline_to_corpus: outline_text=<syllabus>, book_ids=<textbooks>
2. For each topic in coverage_matrix:
   - search_documents: query=<topic>
   - generate_content: instruction="Summarize with key definitions, examples, and practice questions"
3. export_docx: title="Comprehensive Study Guide"
```

**Domains Supported:**
- Education: Course-specific study guides
- Professional certification: Exam preparation guides
- Training: Onboarding guides

---

## Verification via Scenario Tests

The following scenarios should pass to verify these workflows work across domains:

### Scenario 1: Medical Q&A Generation
- **Input:** Medical textbook chapters
- **Workflow:** Extract clinical questions → Retrieve evidence → Generate answers
- **Output:** Q&A pairs with citations to textbook sections
- **Verification:** Answers are medically accurate and properly cited

### Scenario 2: Legal Evidence Table
- **Input:** Multiple case law documents
- **Workflow:** Compare documents on legal principle → Format as evidence table
- **Output:** Table with cases, rulings, reasoning, and precedential value
- **Verification:** Table accurately reflects legal reasoning across cases

### Scenario 3: Engineering Concept Map
- **Input:** Engineering manual
- **Workflow:** Traverse concepts → Generate Mermaid diagram
- **Output**: Visual concept map showing component relationships
- **Verification:** Diagram accurately reflects system architecture

### Scenario 4: Business Timeline
- **Input:** Annual reports (5 years)
- **Workflow:** Extract dates/events → Chronological analysis → Format timeline
- **Output:** Timeline of company milestones and financial events
- **Verification:** Timeline accurately reflects company history

### Scenario 5: Historical Study Guide
- **Input:** History textbook and primary sources
- **Workflow:** Map syllabus to sources → Summarize topics → Compile guide
- **Output:** Comprehensive study guide with citations
- **Verification:** Guide covers all syllabus topics with proper sourcing

---

## Implementation Status

All required tools are already implemented:
- ✅ `extract_items` - Generic structured extraction
- ✅ `search_documents` - RAG retrieval
- ✅ `traverse_concepts` - Knowledge graph traversal
- ✅ `compare_documents` - Document comparison
- ✅ `generate_content` - Free-form content generation
- ✅ `analyze_corpus_trends` - Trend analysis
- ✅ `map_outline_to_corpus` - Outline mapping
- ✅ `export_docx` / `export_markdown` - Document export

The agent can compose these tools dynamically to achieve any of the workflows above without requiring new code. The ResearchAgent's planner determines the optimal tool sequence for each request.

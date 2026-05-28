# API Contracts — AI Notes Creator Model

> Scope: Public contracts only. Internal helpers belong in module specs.
> All names listed here must exist in code with identical signatures (MESO Rule 8).

---

## 1. Pipeline

### 1.1 `run_pipeline`

**Module:** `src/core/pipeline.py`  
**Re-export:** `src/book_pipeline/__init__.py`

```python
def run_pipeline(
    pdf_path: str,
    *,
    enable_logs: bool = False,
    persist_to_db: bool = False,
) -> tuple[PipelineResult, PipelineLogger | None]:
    ...
```

---

## 2. Ingestion

```python
# src/ingestion/pdf_extractor.py
def extract_pdf(pdf_path: str) -> tuple[list, str, dict]: ...

# src/ingestion/text_normalizer.py
def normalize_text(pdf_extraction_result) -> list: ...

# src/ingestion/layout_enrichment.py
def lines_to_log(lines) -> dict: ...

# src/ingestion/service.py
def ingest_pdf(file_path: str) -> IngestedPdf: ...
```

---

## 3. Structure (key stage functions)

```python
def mark_noise(lines): ...
def collect_candidates_scored(lines): ...
def gate_heading_validity_candidates(candidates, lines=...): ...
def apply_continuity_filter(candidates, layout_by_line_id): ...
def build_fragments(normalized, headings): ...
def clean_toc(headings, fragments=...): ...
def detect_deterministic_toc(lines, toc_out): ...
def build_toc_sections_from_repeated_headings(lines, toc_out): ...
def book_metadata_from_first_toc_section(lines, det_section_log): ...
```

---

## 4. CLI

```python
# src/interaction/command_loop.py
class CommandLoop:
    def start(self) -> None: ...

# src/interaction/command_parser.py
class CommandParser:
    @staticmethod
    def parse_intent(user_input: str) -> IntentResult: ...
```

---

## 5. LLM Client

```python
# src/core/llm_chat_client.py
class LlmChatClient:
    @classmethod
    def from_config(cls) -> LlmChatClient: ...
    def chat(self, system_prompt: str, user_prompt: str, *, max_tokens: int | None = None) -> str: ...
```

```python
# src/generation/model_router.py
class RewriteModelRouter:
    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> str: ...
```

---

## 6. Storage

```python
# src/storage/knowledge_store.py
class KnowledgeStore:
    def get_connection(self): ...
    def save_pipeline_artifact(self, ...): ...

# src/storage/book_repository.py
class BookRepository:
    def save_book(self, ...): ...
    def get_book_by_id(self, book_id: int): ...
    def list_all_books(self): ...

# src/storage/toc_repository.py
class TocRepository:
    def save_full_toc(self, ...): ...
    def get_book_toc(self, book_id: int): ...
```

---

## 7. Export

```python
# src/export/word_exporter.py
class WordExporter:
    def structured_text_to_word(self, ...): ...
    def assemble_full_book_structured_text(self, ...): ...

# src/export/output_manager.py
class OutputManager:
    def export_to_word(self, ...): ...
    def handle_output(self, ...): ...
```

---

## 8. Debug

```python
# src/debug/run_toc_trace.py
def run(pdf_path: str) -> Path: ...

# src/debug/visualizer.py
def visualize_run(*, pdf_path: str = ..., run_dir: str = ...) -> Path: ...
```

---

## 9. Logging

```python
# src/structure/logging/pipeline_logger.py
class PipelineLogger:
    @classmethod
    def create(cls, *, pdf_file: str, enabled: bool) -> PipelineLogger | NoOpPipelineLogger: ...
    def write_stage(self, stage_name: str, payload) -> None: ...
```

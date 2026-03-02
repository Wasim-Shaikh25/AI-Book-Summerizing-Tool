from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class HeadingBatcherConfig:
    """
    Stage-1 -> Stage-2 bridge policy.

    Stage 1 produces spans/fragments deterministically.
    This batcher groups them into small LLM-friendly batches.

    IMPORTANT:
    - No model calling here.
    - Only batching + payload prep.
    """
    min_batch_size: int = 10
    max_batch_size: int = 20
    max_preview_words: int = 500


@dataclass(frozen=True)
class HeadingCandidate:
    """
    Final stable candidate after Stage-1 merge.
    `fragment_id` MUST be stable and sequential (assigned post-merge).
    """
    fragment_id: int
    index: int
    title: str
    span_word_count: int
    span_line_count: int
    span_preview: str


@dataclass(frozen=True)
class HeadingBatch:
    batch_id: int
    document_title: str
    headings: List[HeadingCandidate]

    def to_payload(self) -> Dict[str, Any]:
        """
        JSON schema to send to the LLM structural judge.

        Contract:
        - `id` is the stable fragment_id from Stage-1 (NOT a per-batch counter)
        - `index` is the line index in the normalized line stream
        """
        return {
            "document_title": self.document_title,
            "headings": [
                {
                    "id": h.fragment_id,
                    "index": h.index,
                    "title": h.title,
                    "span_word_count": h.span_word_count,
                    "span_line_count": h.span_line_count,
                    "span_preview": h.span_preview,
                }
                for h in self.headings
            ],
        }


def _chunk_sizes(n: int, min_size: int, max_size: int) -> List[int]:
    """
    Deterministic chunking:
    - fill with max_size chunks
    - last chunk is >= min_size when possible by borrowing from previous chunk
    """
    if n <= 0:
        return []
    if n <= max_size:
        return [n]

    sizes: List[int] = []
    remaining = n
    while remaining > 0:
        take = min(max_size, remaining)
        sizes.append(take)
        remaining -= take

    # If last chunk is too small, rebalance with previous chunk.
    if len(sizes) >= 2 and sizes[-1] < min_size:
        need = min_size - sizes[-1]
        borrow = min(need, sizes[-2] - min_size) if sizes[-2] > min_size else 0
        if borrow > 0:
            sizes[-2] -= borrow
            sizes[-1] += borrow

    return sizes


def build_heading_batches(
    document_title: str,
    candidates: List[HeadingCandidate],
    config: Optional[HeadingBatcherConfig] = None,
) -> List[HeadingBatch]:
    """
    Create LLM batches (10–20 max).
    Keeps original ordering.

    If total candidates < min_batch_size, returns single small batch.
    """
    cfg = config or HeadingBatcherConfig()

    ordered = sorted(candidates, key=lambda c: c.index)
    sizes = _chunk_sizes(len(ordered), cfg.min_batch_size, cfg.max_batch_size)

    batches: List[HeadingBatch] = []
    offset = 0
    for batch_id, size in enumerate(sizes, start=1):
        chunk = ordered[offset : offset + size]
        batches.append(
            HeadingBatch(
                batch_id=batch_id,
                document_title=document_title,
                headings=chunk,
            )
        )
        offset += size

    return batches

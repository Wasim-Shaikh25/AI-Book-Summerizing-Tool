from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import List, Sequence

from typing import Any as Block

# Structural reset: local_structure removed.
# This chunker is temporarily disabled until a new boundary scorer is implemented.


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    block_indices: list[int]
    text: str
    token_count: int


class SemanticChunkBuilder:
    """
    Semantic chunk builder (MiniLM only).

    Responsibilities:
      - Use MiniLM CrossEncoder to score transitions between adjacent blocks.
      - Mark strong boundaries when transition_score < threshold.
      - Build chunks up to max_tokens, preferring strong boundaries to split.
      - Add overlap by carrying overlap_tokens worth of previous text into the next chunk.
      - Avoid splitting inside the same paragraph when possible (heuristic).

    Non-responsibilities (explicitly forbidden by prompt):
      - Heading detection
      - Text modification beyond concatenation/whitespace joining
      - Fragment ID assignment
      - Fragment deletion / rewriting
    """

    def __init__(self, *, boundary_threshold: float = 0.55) -> None:
        raise NotImplementedError("Semantic chunk builder not yet implemented.")

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """
        Heuristic token estimation (no tokenizer dependency):
        ~ 1 token ~= 4 characters for English-ish text.
        """
        t = (text or "").strip()
        if not t:
            return 0
        return max(1, int(len(t) / 4))

    @staticmethod
    def _is_paragraph_continuation(prev_text: str, next_text: str) -> bool:
        """
        Best-effort heuristic: treat as "same paragraph" if:
          - previous block does NOT end with strong sentence terminator
          - next block starts with lowercase / punctuation continuation
        This is only used to *avoid splitting* there if we have other options.
        """
        p = (prev_text or "").strip()
        n = (next_text or "").strip()
        if not p or not n:
            return False

        ends_hard = bool(re.search(r'[.!?:"”\)\]]\s*$', p))
        starts_lower = bool(re.match(r"^[a-z]", n))
        starts_continuation = bool(re.match(r"^[,;:\)\]\-]", n))

        return (not ends_hard) and (starts_lower or starts_continuation)

    def _transition_score(self, a: str, b: str) -> float:
        """
        CrossEncoder transition scoring between block_i and block_i+1.

        NOTE:
        This uses the existing StructureCrossEncoderValidator as the MiniLM carrier.
        Per the refactor spec, this module must not do heading classification.
        """
        a = (a or "").strip()
        b = (b or "").strip()
        if not a or not b:
            return 0.0

        # Use CrossEncoder in a "relatedness" way; we only consume the numeric score.
        # This must remain boundary-only usage.
        v = self.validator.validate_heading_candidate(a, b, threshold=self.boundary_threshold)
        return float(v.score)

    def build_chunks(self, blocks: Sequence[Block], max_tokens: int = 1500, overlap_tokens: int = 250) -> List[Chunk]:
        blocks = list(blocks or [])
        if not blocks:
            logger.info("SemanticChunkBuilder: total_chunks=0 avg_chunk_size=0 boundary_count=0")
            return []

        # Precompute transitions and strong boundaries
        strong_boundaries: set[int] = set()  # boundary after index i (split between i and i+1)
        transition_scores: list[float] = []

        for i in range(len(blocks) - 1):
            s = self._transition_score(blocks[i].text, blocks[i + 1].text)
            transition_scores.append(float(s))
            if s < self.boundary_threshold:
                strong_boundaries.add(i)

        boundary_count = len(strong_boundaries)

        # Build chunks
        chunks: list[Chunk] = []
        n = len(blocks)
        i = 0

        while i < n:
            start = i
            cur_indices: list[int] = []
            cur_text_parts: list[str] = []
            cur_tokens = 0

            # Grow chunk until max_tokens
            j = i
            while j < n:
                bt = (blocks[j].text or "").strip()
                if bt:
                    bt_tokens = self._estimate_tokens(bt)
                else:
                    bt_tokens = 0

                # If adding this block would exceed max_tokens, stop (but don't create empty chunk)
                if cur_indices and (cur_tokens + bt_tokens) > int(max_tokens):
                    break

                cur_indices.append(j)
                if bt:
                    cur_text_parts.append(bt)
                cur_tokens += bt_tokens
                j += 1

            # If we stopped because of max_tokens, prefer splitting earlier at a strong boundary
            # inside [start, j-1] (boundary after k where k in [start, j-2]).
            if j < n and cur_indices:
                # candidate split points are after k => chunk end at k, next starts at k+1
                candidates = [k for k in range(start, cur_indices[-1]) if k in strong_boundaries]

                # Avoid splitting inside same paragraph when choosing candidate
                filtered: list[int] = []
                for k in candidates:
                    prev_t = blocks[k].text
                    next_t = blocks[k + 1].text if (k + 1) < n else ""
                    if self._is_paragraph_continuation(prev_t, next_t):
                        continue
                    filtered.append(k)

                chosen_k = None
                if filtered:
                    chosen_k = max(filtered)  # latest strong boundary within current window
                elif candidates:
                    chosen_k = max(candidates)  # fallback: allow paragraph split if no alternative

                if chosen_k is not None:
                    # Rebuild chunk to end at chosen_k
                    cur_indices = list(range(start, chosen_k + 1))
                    cur_text_parts = [(blocks[idx].text or "").strip() for idx in cur_indices if (blocks[idx].text or "").strip()]
                    cur_text = "\n\n".join(cur_text_parts)
                    cur_tokens = self._estimate_tokens(cur_text)
                    j = chosen_k + 1  # next start

            # Safety: ensure progress even if a single block exceeds max_tokens
            if not cur_indices:
                cur_indices = [i]
                bt = (blocks[i].text or "").strip()
                cur_text_parts = [bt] if bt else []
                cur_text = "\n\n".join(cur_text_parts)
                cur_tokens = self._estimate_tokens(cur_text)
                j = i + 1

            # Finalize current chunk
            cur_text = "\n\n".join(cur_text_parts)
            chunks.append(
                Chunk(
                    chunk_id=str(uuid.uuid4()),
                    block_indices=cur_indices,
                    text=cur_text,
                    token_count=int(cur_tokens),
                )
            )

            # Compute next start with overlap
            next_start = j
            if next_start >= n:
                break

            if overlap_tokens > 0:
                # Walk backwards from end of current chunk to accumulate overlap tokens
                overlap_indices: list[int] = []
                overlap_acc = 0
                for idx in reversed(cur_indices):
                    t = (blocks[idx].text or "").strip()
                    if not t:
                        continue
                    overlap_acc += self._estimate_tokens(t)
                    overlap_indices.append(idx)
                    if overlap_acc >= int(overlap_tokens):
                        break
                overlap_indices = sorted(set(overlap_indices))

                # Ensure overlap is contiguous and ends at last index of previous chunk
                if overlap_indices:
                    next_start = min(next_start, overlap_indices[0])

            # Avoid infinite loops
            if next_start <= start:
                next_start = j

            i = next_start

        avg_chunk_size = (sum(c.token_count for c in chunks) / float(len(chunks))) if chunks else 0.0
        logger.info(
            "SemanticChunkBuilder: total_chunks=%s avg_chunk_size=%.2f boundary_count=%s",
            len(chunks),
            avg_chunk_size,
            boundary_count,
        )
        return chunks

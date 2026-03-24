from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from src.core.models import HeadingCandidate, NormalizedLine

# Optional local embedding-based gate (kept inside this file as requested).
# Uses sentence-transformers MiniLM embeddings to drop ultra-low-likelihood headings.
# This is designed to be conservative: only drops when confidence is extremely high.
try:
    from sentence_transformers import SentenceTransformer
    import numpy as _np
except Exception:  # pragma: no cover
    SentenceTransformer = None  # type: ignore[assignment]
    _np = None  # type: ignore[assignment]


_WS_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"\b\w+\b")
_PAGE_OF_RE = re.compile(r"^page\s*\d+\s*(of\s*\d+)?\s*$", re.IGNORECASE)
_ROMAN_RE = re.compile(r"^(?=[MDCLXVI])M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})\.?$", re.IGNORECASE)

# Enumerated-body patterns we can safely drop before LLM.
# Goal: remove "1. This is a sentence..." / "a) This is a sentence..." which are almost always body text.
_ENUM_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"\d{1,3}\s*[\.\)]"  # 1. / 1)
    r"|[a-zA-Z]\s*[\.\)]"  # a. / a)
    r"|[ivxlcdm]{1,6}\s*[\.\)]"  # i. / iv) (roman)
    r")\s+"
)
# True headings often look like 1.1 / 2.3.4; we should NOT treat those as enumerated-body.
_DECIMAL_SECTION_RE = re.compile(r"^\s*\d+(\.\d+){1,6}\b")
# Cheap sentence signals (domain agnostic)
_SENTENCE_SIGNAL_RE = re.compile(r"[,\.;:]\s|(?:\bwhich\b|\bthat\b|\bis\b|\bare\b|\bwas\b|\bwere\b|\bhas\b|\bhave\b)", re.IGNORECASE)

_MINILM_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_MINILM: Any = None  # lazy-loaded singleton


def _word_count(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


def _is_obvious_noise_heading(text: str) -> bool:
    """
    Ultra-high confidence "not a heading" patterns.

    Important: still domain-agnostic (no MODULE/UNIT/etc. keywords).
    """
    t = (text or "").strip()
    if not t:
        return False

    # Standalone page markers like "Page 1" / "Page 1 of 133"
    if _PAGE_OF_RE.match(t):
        return True

    # Pure numbers / page numbers / section numbers with nothing else.
    if re.fullmatch(r"\d{1,4}", t):
        return True
    if re.fullmatch(r"\d{1,4}\s*/\s*\d{1,4}", t):
        return True

    # Roman numeral alone (I, II, IV, etc.) is frequently a list marker / page header artifact
    if _ROMAN_RE.match(t):
        return True

    # Single-letter bullets like "a)" "b)" etc. with no other content are not headings
    if re.fullmatch(r"[a-zA-Z]\)", t):
        return True

    return False


def _is_paragraph_like(text: str) -> bool:
    """
    Conservative heuristic: identify lines that are almost certainly body sentences.

    We intentionally do NOT use domain keywords (UNIT/MODULE/CHAPTER/etc.). This is universal.

    Returns True only when confidence is high.
    """
    t = (text or "").strip()
    if not t:
        return False

    # If it clearly looks like a sentence/paragraph (length + punctuation).
    # Use lower thresholds than before because the scorer is selecting many body lines.
    if len(t) >= 160:
        return True

    wc = _word_count(t)

    # Long line with commas/periods tends to be body text, not headings.
    if wc >= 18 and (t.endswith(".") or t.count(",") >= 2):
        return True

    # If it contains multiple sentences, it's not a heading.
    # (We keep this conservative: 2+ periods and long enough.)
    if len(t) >= 140 and t.count(".") >= 2:
        return True

    return False


def _is_too_empty(text: str) -> bool:
    return (text or "").strip() == ""


def _looks_like_body_sentence(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False

    wc = _word_count(t)
    if wc >= 14:
        return True

    # sentence-ish punctuation / common glue words
    if wc >= 10 and _SENTENCE_SIGNAL_RE.search(t):
        return True

    # Ends with a period and is not tiny
    if wc >= 8 and t.endswith("."):
        return True

    return False


def _is_enumerated_body_line(text: str) -> bool:
    """
    Drop enumerated prose lines like:
      - "1. The Tort is of French origin..."
      - "a) It may be an act which..."
    Keep:
      - "1.1 Tort: Definition ..." (TOC-like)
      - short enumerated headings like "1. Introduction"
    """
    t = (text or "").strip()
    if not t:
        return False

    # Keep decimal section headings (1.1 / 2.3.4) - common in TOCs.
    if _DECIMAL_SECTION_RE.match(t):
        return False

    if not _ENUM_PREFIX_RE.match(t):
        return False

    # If it's enumerated and sentence-like, it's almost surely body text.
    if _looks_like_body_sentence(t):
        return True

    return False


def _starts_with_lowercase_letter(text: str) -> bool:
    """
    Many false positives are mid-paragraph lines that start in lowercase (e.g. "of tort still awaits...").
    True headings rarely start with lowercase letters.
    """
    t = (text or "").strip()
    if not t:
        return False
    return bool(re.match(r"^[a-z]", t))


def _starts_with_capital_letter(text: str) -> bool:
    t = (text or "").lstrip()
    if not t:
        return False
    return bool(re.match(r"^[A-Z]", t))


def _is_non_bold_lowercase_fake_heading(*, c: HeadingCandidate, first_ln: NormalizedLine | None) -> bool:
    """
    Deterministic filter requested:
      - Drop if NOT bold AND starts with lowercase
      - Keep exceptions:
        - decimal section headings like "1.2 Something" (common in TOCs)
        - if we have no layout line info
    """
    if first_ln is None:
        return False

    # Keep true section numbering headings even if not bold.
    if _DECIMAL_SECTION_RE.match((c.text or "").strip()):
        return False

    # Only apply when clearly not bold.
    if getattr(first_ln, "is_bold", False):
        return False

    return _starts_with_lowercase_letter(c.text or "")


def _normalize_reason(reason: str) -> str:
    return _WS_RE.sub(" ", (reason or "").strip())


def _get_minilm() -> Any:
    """
    Lazy load MiniLM embedding model. Kept local to avoid changing other modules.
    Returns None if sentence-transformers is unavailable.
    """
    global _MINILM
    if SentenceTransformer is None:
        return None
    if _MINILM is None:
        # CPU default. If torch has CUDA, sentence-transformers can pick it up automatically,
        # but we don't force it here.
        _MINILM = SentenceTransformer(_MINILM_MODEL_NAME)
    return _MINILM


def _cosine_sim_matrix(vectors: Any) -> Any:
    # vectors: np.ndarray shape (n, d)
    # return: np.ndarray shape (n, n)
    if _np is None:
        return None
    v = vectors.astype("float32", copy=False)
    denom = _np.linalg.norm(v, axis=1, keepdims=True) + 1e-12
    v = v / denom
    return v @ v.T


def _embedding_gate_is_fake_heading(
    *,
    text: str,
    neighbors: List[str],
    threshold: float = 0.88,
    use_centroid: bool = True,
) -> Tuple[bool, str]:
    """
    Embedding-based filter:
      - Compare candidate to its nearby CONTEXT lines (before/after).
      - If use_centroid=True, also compare to the centroid of the context window.
        This acts like a “paragraph continuity” check.

    We only drop when similarity is high to avoid false negatives.
    """
    model = _get_minilm()
    if model is None or _np is None:
        return False, ""

    t = (text or "").strip()
    neigh = [(n or "").strip() for n in neighbors if (n or "").strip()]
    if not t or not neigh:
        return False, ""

    # Encode candidate + neighbors in one call
    items = [t] + neigh
    try:
        emb = model.encode(items, normalize_embeddings=True)
    except Exception:
        return False, ""

    cand = emb[0]

    # IMPORTANT SAFETY: avoid dropping very short Q/A style headings just because they're similar.
    wc = _word_count(t)
    if wc <= 4:
        return False, ""

    # Similarity to individual neighbor lines
    sims = [float(cand @ emb[i]) for i in range(1, len(items))]
    max_line_sim = max(sims) if sims else 0.0

    # Similarity to centroid (paragraph-ish)
    centroid_sim = 0.0
    if use_centroid and len(items) >= 3 and _np is not None:
        ctx = emb[1:]
        centroid = _np.mean(ctx, axis=0)
        # normalize
        denom = float(_np.linalg.norm(centroid) + 1e-12)
        centroid = centroid / denom
        centroid_sim = float(cand @ centroid)

    score = max(max_line_sim, centroid_sim)

    if score >= float(threshold):
        return True, (
            f"embedding_context_similarity={score:.3f} "
            f"(line_max={max_line_sim:.3f}, centroid={centroid_sim:.3f}, >= {float(threshold):.2f})"
        )
    return False, ""


def _page_body_centroids(
    *,
    lines: Sequence[NormalizedLine],
    exclude_line_ids: set[int],
    min_len: int = 20,
    max_lines_per_page: int = 80,
) -> Dict[int, Any]:
    """
    Build per-page centroid embeddings of likely BODY text lines.

    - Uses only non-noise lines with enough characters.
    - Excludes lines that are candidate headings (by line_id) to avoid contaminating the body centroid.
    - Caps lines per page for speed.
    """
    model = _get_minilm()
    if model is None or _np is None:
        return {}

    # Collect body text by page
    by_page: Dict[int, List[str]] = {}
    for ln in lines:
        try:
            lid = int(getattr(ln, "line_id"))
        except Exception:
            continue
        if lid in exclude_line_ids:
            continue
        if getattr(ln, "is_noise", False):
            continue
        txt = (getattr(ln, "text", "") or "").strip()
        if len(txt) < min_len:
            continue

        pn = int(getattr(ln, "page_number", 0) or 0)
        if pn <= 0:
            pn = 0
        by_page.setdefault(pn, [])
        if len(by_page[pn]) < max_lines_per_page:
            by_page[pn].append(txt)

    centroids: Dict[int, Any] = {}
    for pn, texts in by_page.items():
        if len(texts) < 6:
            continue
        try:
            emb = model.encode(texts, normalize_embeddings=True)
        except Exception:
            continue
        centroid = _np.mean(emb, axis=0)
        denom = float(_np.linalg.norm(centroid) + 1e-12)
        centroid = centroid / denom
        centroids[pn] = centroid

    return centroids


def gate_heading_validity_candidates(
    candidates: Sequence[HeadingCandidate],
    *,
    lines: Sequence[NormalizedLine] | None = None,
) -> Tuple[List[HeadingCandidate], List[Dict[str, Any]]]:
    """
    Pre-LLM gate for heading validity.

    Goal:
      - Reduce obvious non-headings BEFORE calling the LLM.
      - Be conservative: only drop when we're extremely confident.

    Notes:
      - Noise lines are already excluded earlier by candidate scoring (ln.is_noise).
        This gate is a safety layer for other call paths + paragraph-like junk.
      - This function does NOT mutate candidates; it returns a filtered list.
    """
    kept: List[HeadingCandidate] = []
    log: List[Dict[str, Any]] = []

    # Optional layout lookup (for "bold+Capital never drop" safeguard)
    line_by_id: Dict[int, NormalizedLine] = {}
    if lines is not None:
        line_by_id = {int(ln.line_id): ln for ln in lines if hasattr(ln, "line_id")}

    # Optional MiniLM per-page body centroid embeddings (used only for non-bold candidates).
    page_centroids: Dict[int, Any] = {}
    if lines is not None and SentenceTransformer is not None and _np is not None:
        exclude_ids: set[int] = set()
        for c in candidates:
            try:
                exclude_ids.add(int(c.start_line))
            except Exception:
                pass
        page_centroids = _page_body_centroids(lines=lines, exclude_line_ids=exclude_ids)

    for idx, c in enumerate(candidates):
        text = c.text or ""
        reasons: List[str] = []

        # HARD RULE: if the candidate has strong layout heading signals, never drop it in this stage.
        #
        # Rationale: PyMuPDF-derived layout features are higher precision than semantic similarity
        # (real headings are often semantically similar to adjacent body paragraphs).
        #
        # Protected if ANY of:
        # - bold
        # - large font (relative to page median)
        # - large vertical gap above (relative to page median)
        # - centered on the page
        if line_by_id:
            first_ln = line_by_id.get(int(c.start_line))
            t_strip = (text or "").lstrip()
            starts_cap = bool(t_strip) and bool(re.match(r"^[A-Z]", t_strip))
            if first_ln is not None:
                strong_layout = bool(
                    getattr(first_ln, "is_bold", False)
                    or getattr(first_ln, "large_font", False)
                    or getattr(first_ln, "large_gap", False)
                    or getattr(first_ln, "centered", False)
                )
                if strong_layout and starts_cap:
                    kept.append(c)
                    continue


        if _is_too_empty(text):
            reasons.append("empty_text")

        if _is_obvious_noise_heading(text):
            reasons.append("obvious_noise")

        if _is_paragraph_like(text):
            reasons.append("paragraph_like")

        if _is_enumerated_body_line(text):
            reasons.append("enumerated_body_line")

        if _starts_with_lowercase_letter(text):
            reasons.append("starts_with_lowercase")

        # Extra deterministic filter: if the candidate line is not bold and starts lowercase,
        # it is extremely likely to be mid-paragraph body text.
        if line_by_id:
            first_ln = line_by_id.get(int(c.start_line))
            if _is_non_bold_lowercase_fake_heading(c=c, first_ln=first_ln):
                reasons.append("not_bold_and_starts_lowercase")

        # MiniLM continuity gate: compare candidate to its local paragraph context (before/after)
        neigh = []
        neigh.extend(list(getattr(c, "before_context", []) or [])[-5:])
        neigh.extend(list(getattr(c, "after_context", []) or [])[:5])

        from src import config as cfg

        # MiniLM continuity gate:
        # Apply ONLY when the candidate does NOT have strong layout heading signals.
        # This avoids dropping valid headings that are semantically similar to nearby body text.
        t_norm = (text or "").strip()
        is_title_case = bool(re.match(r"^[A-Z][A-Za-z0-9'’\-]*(?:\s+[A-Z][A-Za-z0-9'’\-]*){1,}$", t_norm))

        strong_layout = False
        if line_by_id:
            first_ln = line_by_id.get(int(c.start_line))
            if first_ln is not None:
                strong_layout = bool(
                    getattr(first_ln, "is_bold", False)
                    or getattr(first_ln, "large_font", False)
                    or getattr(first_ln, "large_gap", False)
                    or getattr(first_ln, "centered", False)
                )

        if (not strong_layout) and (not is_title_case):
            thr = float(getattr(cfg, "MINILM_FAKE_HEADING_SIM_THRESHOLD", None) or "0.88")
            is_fake, embed_reason = _embedding_gate_is_fake_heading(
                text=t_norm,
                neighbors=neigh,
                threshold=thr,
                use_centroid=True,
            )
            if is_fake:
                reasons.append(f"embedding_fake({embed_reason})")

        # MiniLM page-body centroid gate (requested): if candidate is semantically too close
        # to the overall page body, it's likely body text. Apply only to non-bold candidates.
        if line_by_id and page_centroids:
            first_ln = line_by_id.get(int(c.start_line))
            if first_ln is not None and not getattr(first_ln, "is_bold", False):
                pn = int(getattr(first_ln, "page_number", 0) or 0)
                centroid = page_centroids.get(pn)
                if centroid is None:
                    centroid = page_centroids.get(0)
                if centroid is not None and SentenceTransformer is not None and _np is not None:
                    model = _get_minilm()
                    if model is not None:
                        try:
                            cand_emb = model.encode([(text or "").strip()], normalize_embeddings=True)[0]
                            sim = float(cand_emb @ centroid)
                            thr2 = float(getattr(cfg, "MINILM_PAGE_BODY_SIM_THRESHOLD", None) or "0.80")
                            if _word_count((text or "").strip()) > 4 and sim >= thr2:
                                reasons.append(f"embedding_page_body(sim={sim:.3f} >= {thr2:.2f})")
                        except Exception:
                            pass

        if reasons:
            log.append(
                {
                    "heading_id": c.id,
                    "text": c.text,
                    "action": "drop_before_llm_validity",
                    "reason": _normalize_reason(", ".join(reasons)),
                }
            )
            continue

        kept.append(c)

    return kept, log


def gate_toc_candidates(
    headings: Sequence[HeadingCandidate],
) -> Tuple[List[HeadingCandidate], List[Dict[str, Any]]]:
    """
    Pre-LLM gate for TOC classification.

    Goal:
      - Do not spend TOC LLM calls on headings that are already invalid.
      - Also drop extremely confident junk lines.

    Policy:
      - Drop if is_valid == False
      - Keep if is_valid is None (unknown)
      - Keep if is_valid == True (valid)
    """
    kept: List[HeadingCandidate] = []
    log: List[Dict[str, Any]] = []

    for h in headings:
        text = h.text or ""
        reasons: List[str] = []

        if h.is_valid is False:
            reasons.append("is_valid_false")

        if _is_too_empty(text):
            reasons.append("empty_text")

        if _is_obvious_noise_heading(text):
            reasons.append("obvious_noise")

        if _is_paragraph_like(text):
            reasons.append("paragraph_like")

        if reasons:
            log.append(
                {
                    "heading_id": h.id,
                    "text": h.text,
                    "action": "drop_before_llm_toc",
                    "reason": _normalize_reason(", ".join(reasons)),
                    "is_valid": h.is_valid,
                    "is_toc": h.is_toc,
                }
            )
            continue

        kept.append(h)

    return kept, log

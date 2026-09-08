from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from src.shared.models import HeadingCandidate, NormalizedLine

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
_CONTINUATION_CONJUNCTIONS_RE = re.compile(
    r"^(?:and|but|or|nor|so|yet|which|that|who|whom|whose|when|where|"
    r"because|although|though|since|unless|until|while|as|if)\b",
    re.IGNORECASE,
)
_PAGE_OF_RE = re.compile(r"^page\s*\d+\s*(of\s*\d+)?\s*$", re.IGNORECASE)
# Spaced-letter page footer variants: "29| P a g e", "P a g e | 13", "P a g e"
_SPACED_PAGE_RE = re.compile(
    r"^\s*(?:\d+\s*\|?\s*)?[Pp]\s*[Aa]\s*[Gg]\s*[Ee]\s*(?:\|?\s*\d+)?\s*$"
)
_ROMAN_RE = re.compile(r"^(?=[MDCLXVI])M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})\.?$", re.IGNORECASE)

# Enumerated-body patterns we can safely drop in the deterministic gate.
# Goal: remove "1. This is a sentence..." / "a) This is a sentence..." which are almost always body text.
_ENUM_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"\d{1,3}\s*[\.\)]"  # 1. / 1)
    r"|[a-zA-Z]\s*[\.\)]"  # a. / a)
    r"|[ivxlcdm]{1,6}\s*[\.\)]"  # i. / iv) (roman)
    r")\s+"
)
# True headings often look like 1.1 / 2.3.4; we should NOT treat those as enumerated-body.
_DECIMAL_SECTION_RE = re.compile(r"^\s*\d+(\.\s*\d+){1,6}\b")
# Cheap sentence signals (domain agnostic)
_SENTENCE_SIGNAL_RE = re.compile(r"[,\.;:]\s|(?:\bwhich\b|\bthat\b|\bis\b|\bare\b|\bwas\b|\bwere\b|\bhas\b|\bhave\b)", re.IGNORECASE)

_MINILM_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_MINILM: Any = None  # lazy-loaded singleton


def _word_count(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


_TRAILING_FUNC_WORD_RE = re.compile(
    r"\b(?:the|a|an|of|in|to|for|with|from|by|at|on|and|or|is|are|was|were|that|which|this|be|has|have|its|their|his|her|it|as)\s*$",
    re.IGNORECASE,
)
_HYPHEN_SLUG_RE = re.compile(r"\b\w+(-\w+){3,}\b")


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

    # Spaced-letter page footers: "29| P a g e", "P a g e | 13", "P a g e"
    if _SPACED_PAGE_RE.match(t):
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


def _is_paragraph_like(text: str, is_bold: bool = False, is_mix_bold: bool = False) -> bool:
    """
    Conservative heuristic: identify lines that are almost certainly body sentences.

    We intentionally do NOT use domain keywords (UNIT/MODULE/CHAPTER/etc.). This is universal.

    Returns True only when confidence is high.

    Important: decimal TOC-like headings such as "1.1 Tort: Definition, ..." must not be
    rejected merely because they contain commas or colons. Those are common in legal TOCs.
    
    NEW: Don't penalize : and , in fully bold lines. Reject mixed bold lines.
    """
    t = (text or "").strip()
    if not t:
        return False

    # NEW: Reject mixed bold lines immediately
    if is_mix_bold:
        return True

    wc = _word_count(t)

    # Protect TOC-like decimal headings even if they contain punctuation and look sentence-like.
    if _DECIMAL_SECTION_RE.match(t):
        if wc <= 16:
            return False
        if len(t) <= 110 and (t.count(",") <= 2 or t.count(":") <= 1):
            return False

    # NEW: Don't penalize : and , in fully bold lines
    punctuation_to_check = [";", "."]
    if not is_bold:
        punctuation_to_check.extend([",", ":"])

    # Strong body-text signal: long prose-like lines with sentence punctuation.
    if wc >= 8 and len(t) >= 70:
        if any(punct in t for punct in punctuation_to_check):
            return True

    # Sentence-style lines with common glue words and enough length are likely body text.
    if wc >= 10 and _SENTENCE_SIGNAL_RE.search(t):
        return True

    # Multiple clauses/sentences almost never indicate a heading.
    if len(t) >= 100 and t.count(".") >= 2:
        return True

    # Medium-length lines that start like a sentence are likely body text.
    if wc >= 7 and _starts_with_capital_letter(t) and t.endswith("."):
        return True

    return False


def _is_too_empty(text: str) -> bool:
    return (text or "").strip() == ""


def _looks_like_body_sentence(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False

    wc = _word_count(t)
    if wc >= 10 and len(t) >= 60:
        return True

    # sentence-ish punctuation / common glue words
    if wc >= 8 and _SENTENCE_SIGNAL_RE.search(t):
        return True

    # Ends with a period and is not tiny
    if wc >= 6 and t.endswith("."):
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
      - legal TOC-style decimal entries that contain punctuation but are still title-like
      - lettered subheadings like "a. Distinction between ..." (common in notes/books)
    """
    t = (text or "").strip()
    if not t:
        return False

    # Keep decimal section headings (1.1 / 2.3.4) - common in TOCs.
    if _DECIMAL_SECTION_RE.match(t):
        if _word_count(t) <= 16 and len(t) <= 120:
            return False

    if not _ENUM_PREFIX_RE.match(t):
        return False

    # Keep "a. Title Case ..." / "b. who may sue ..." style subheadings.
    # These often start with a lowercase letter due to enumeration, but function as headings.
    if re.match(r"^\s*[a-zA-Z]\.\s+\S", t):
        # Allow longer subheadings too (common in law texts): keep unless it clearly looks like prose.
        # Example to keep: "a. Distinction between Crime and Breach of Contract"
        # Example to drop: "a) It may be an act which, without lawful justification..."
        #
        # IMPORTANT: `_looks_like_body_sentence()` treats any >=10-word line as sentence-like,
        # which is too aggressive for these enumerated subheadings.
        #
        # Your rule: if it's a short FULL-BOLD `a.`/`b.` line, keep it even if it starts lowercase.
        # We implement this by only dropping `a.`/`b.` entries when they contain explicit prose markers.
        #
        # "default which we are considering for others" -> use the same shortness thresholds used elsewhere:
        # wc <= 12, len <= 90.
        if not _SENTENCE_SIGNAL_RE.search(t):
            return False

    # If it's enumerated and sentence-like, it's almost surely body text.
    if _looks_like_body_sentence(t):
        return True

    # Even without obvious sentence glue, numbered prose lines are usually body text.
    if _word_count(t) >= 8 and len(t) >= 50:
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
    t = (text or "").strip()
    return bool(t) and bool(re.match(r"^[A-Z]", t))


def _is_multi_line_bold_heading(candidate: Any, lines_by_id: Dict[int, Any]) -> bool:
    """
    Detect if a heading candidate extends across multiple lines with full bold formatting.
    Reject headings that span across 2+ consecutive lines all in bold.
    """
    if not lines_by_id or not hasattr(candidate, 'start_line') or not hasattr(candidate, 'end_line'):
        return False
    
    try:
        start_line = int(candidate.start_line)
        end_line = int(candidate.end_line)
        
        # Check if spans multiple lines (more than 1 line difference)
        if end_line - start_line >= 2:  # Spans 3+ lines (current, next, and third)
            consecutive_bold_lines = 0
            current_line = start_line
            
            while current_line <= end_line and current_line in lines_by_id:
                line_obj = lines_by_id[current_line]
                if getattr(line_obj, "is_bold", False) and not getattr(line_obj, "is_mix_bold", False):
                    consecutive_bold_lines += 1
                else:
                    break
                current_line += 1
            
            # Reject if we have 3+ consecutive bold lines
            if consecutive_bold_lines >= 3:
                return True
                
    except Exception:
        pass
    
    return False


def _has_mixed_bold_segments(line: NormalizedLine | None) -> bool:
    if line is None:
        return False
    return bool(getattr(line, "is_mix_bold", False))


def _is_list_like_numbered_candidate(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(
        re.match(r"^\d+(\.\d+)*\s+[A-Za-z]", t)
        or re.match(r"^[IVXLCDM]+\.\s+[A-Za-z]", t, re.IGNORECASE)
        or re.match(r"^[A-Z]\.\s+[A-Za-z]", t)
    )


def _continuation_context_check(
    candidate_text: str,
    before_lines: list[str],
    after_lines: list[str],
) -> bool:
    """Return True when syntactic context strongly suggests the candidate is a
    continuation fragment rather than a heading.

    Signal 1 — previous line ends mid-sentence AND candidate starts lowercase or
               with a conjunction: the candidate is the second half of a sentence.
    Signal 2 — candidate is >5 words AND the very next line starts lowercase:
               the candidate is a mid-paragraph line, not a heading that introduces
               what follows.

    Both signals are purely syntactic; no domain vocabulary is used.
    """
    text = (candidate_text or "").strip()
    if not text:
        return False

    if before_lines:
        prev = (before_lines[-1] or "").strip()
        if prev and prev[-1] not in ".!?:;":
            if text[0].islower():
                return True
            if _CONTINUATION_CONJUNCTIONS_RE.match(text):
                return True

    if after_lines and len(text.split()) > 5:
        nxt = (after_lines[0] or "").strip()
        if nxt and nxt[0].islower():
            return True

    return False


def _needs_continuity_check(c: HeadingCandidate, first_ln: NormalizedLine | None) -> bool:
    text = (c.text or "").strip()
    if first_ln is None:
        return False
    if getattr(first_ln, "is_bold", False) and _starts_with_lowercase_letter(text):
        return True
    if _is_list_like_numbered_candidate(text):
        return True
    if getattr(first_ln, "is_bold", False) and len(text.split()) >= 3 and len(text) >= 18:
        return True
    return False


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
    Deterministic gate for heading validity.

    Goal:
      - Reduce obvious non-headings using layout and embedding heuristics only.
      - Be conservative: only drop when we're extremely confident.

    Notes:
      - Noise lines are already excluded earlier by candidate scoring (ln.is_noise).
        This gate is a safety layer for other call paths + paragraph-like junk.
      - This function does NOT mutate candidates; it returns a filtered list.
    """
    kept: List[HeadingCandidate] = []
    log: List[Dict[str, Any]] = []
    dropped: List[HeadingCandidate] = []

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
        signals: List[str] = []

        # HARD RULE (priority 0): drop headings whose source line is inside a table or image OCR block.
        # Table headers and image captions should never be treated as document headings.
        if line_by_id:
            _src_ln = line_by_id.get(int(c.start_line))
            if _src_ln is not None and getattr(_src_ln, "source", "") in ("table", "image_ocr"):
                log.append({
                    "id": c.id,
                    "text": c.text,
                    "decision": "dropped",
                    "reason": "inside_table_or_image",
                    "source": getattr(_src_ln, "source", ""),
                    "page_number": getattr(_src_ln, "page_number", None),
                })
                dropped.append(c)
                continue

        # HARD RULE: if the candidate has strong layout heading signals, never drop it in this stage.
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
                is_numbered_sec = bool(_DECIMAL_SECTION_RE.match(t_strip))
                t_wc = _word_count(t_strip)
                max_wc = 20 if is_numbered_sec else 13
                ends_with_func_word = bool(_TRAILING_FUNC_WORD_RE.search(t_strip))
                has_slug = bool(_HYPHEN_SLUG_RE.search(t_strip))
                
                if (strong_layout and starts_cap
                        and t_wc <= max_wc
                        and not ends_with_func_word
                        and not has_slug):
                    signals.append("strong_layout_heading")
                    kept.append(
                        HeadingCandidate(
                            id=c.id,
                            text=c.text,
                            start_line=c.start_line,
                            end_line=c.end_line,
                            before_context=list(c.before_context),
                            after_context=list(c.after_context),
                            full_context_preview=c.full_context_preview,
                            is_valid=c.is_valid,
                            valid_reason=c.valid_reason,
                            is_toc=c.is_toc,
                            toc_reason=c.toc_reason,
                            confidence=c.confidence,
                        )
                    )
                    continue
                leading_spaces = len(text) - len((text or "").lstrip(" "))
                if not strong_layout and leading_spaces >= 2:
                    sentence_like_spaced = (
                        _word_count(t_strip) >= 10
                        and (
                            t_strip.endswith(".")
                            or t_strip.count(",") >= 2
                            or t_strip.count(".") >= 2
                            or bool(re.search(r"\b(?:which|that|is|are|was|were|has|have)\b", t_strip, re.IGNORECASE))
                        )
                    )
                    if sentence_like_spaced and not _DECIMAL_SECTION_RE.match(t_strip):
                        reasons.append("indented_sentence_like_body_text")
                        signals.append("indented_spacing_body_like")

        if _is_too_empty(text):
            reasons.append("empty_text")
            signals.append("empty_text")
        if _is_obvious_noise_heading(text):
            reasons.append("obvious_noise")
            signals.append("obvious_noise")
        # Extract bold information from line if available
        is_bold = False
        is_mix_bold = False
        if line_by_id and int(c.start_line) in line_by_id:
            line_obj = line_by_id[int(c.start_line)]
            is_bold = getattr(line_obj, "is_bold", False)
            is_mix_bold = getattr(line_obj, "is_mix_bold", False)
        
        # NEW: Reject multi-line bold headings
        if _is_multi_line_bold_heading(c, line_by_id):
            reasons.append("multi_line_bold_heading")
            signals.append("multi_line_bold_heading")
        
        if _is_paragraph_like(text, is_bold=is_bold, is_mix_bold=is_mix_bold):
            reasons.append("paragraph_like")
            signals.append("paragraph_like")
        if _is_enumerated_body_line(text):
            reasons.append("enumerated_body_line")
            signals.append("enumerated_body_line")
        if _DECIMAL_SECTION_RE.match((text or "").strip()):
            if _word_count(text) <= 16 and len((text or "").strip()) <= 120:
                if "paragraph_like" in reasons:
                    reasons.remove("paragraph_like")
                if "enumerated_body_line" in reasons:
                    reasons.remove("enumerated_body_line")
                if "paragraph_like" in signals:
                    signals.remove("paragraph_like")
                if "enumerated_body_line" in signals:
                    signals.remove("enumerated_body_line")
        if _starts_with_lowercase_letter(text):
            reasons.append("starts_with_lowercase")
            signals.append("starts_with_lowercase")

        # Mixed bold/normal proxy -> reject as heading
        if line_by_id:
            first_ln = line_by_id.get(int(c.start_line))
            if _has_mixed_bold_segments(first_ln):
                reasons.append("mixed_bold_segments")
                signals.append("mixed_bold_segments")

            if _is_non_bold_lowercase_fake_heading(c=c, first_ln=first_ln):
                reasons.append("not_bold_and_starts_lowercase")
                signals.append("not_bold_and_starts_lowercase")

        # Syntactic continuation-fragment check.
        # Runs only for candidates that did NOT short-circuit via strong_layout_heading.
        # Cheap (no model): drop when context lines prove this is mid-sentence prose.
        _before_ctx = list(getattr(c, "before_context", []) or [])
        _after_ctx = list(getattr(c, "after_context", []) or [])
        if _continuation_context_check(text, _before_ctx, _after_ctx):
            reasons.append("continuation_fragment")
            signals.append("continuation_fragment")

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

        first_ln = line_by_id.get(int(c.start_line)) if line_by_id else None
        if _is_list_like_numbered_candidate(text):
            signals.append("needs_continuity_check")
        if _needs_continuity_check(c, first_ln):
            signals.append("needs_continuity_check")

        if reasons:
            reason_text = _normalize_reason(", ".join(reasons))
            log.append(
                {
                    "heading_id": c.id,
                    "text": c.text,
                    "action": "drop_heading_validity_gate",
                    "reason": reason_text,
                    "signals": sorted(set(signals)),
                }
            )
            dropped.append(
                HeadingCandidate(
                    id=c.id,
                    text=c.text,
                    start_line=c.start_line,
                    end_line=c.end_line,
                    before_context=list(c.before_context),
                    after_context=list(c.after_context),
                    full_context_preview=c.full_context_preview,
                    is_valid=False,
                    valid_reason=reason_text,
                    is_toc=c.is_toc,
                    toc_reason=c.toc_reason,
                    confidence=c.confidence,
                )
            )
            continue

        kept_c = c
        kept.append(kept_c)

    return kept, log

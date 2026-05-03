"""
Deterministic continuity filter: turns scored candidates into FinalHeading rows.

Extracted from src.core.pipeline so the orchestrator stays thin; logic is unchanged.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from src.core.models import FinalHeading


def parse_line_id_from_heading_id(hid: Any) -> Optional[int]:
    if not isinstance(hid, str):
        return None
    if not hid.startswith("L"):
        return None
    try:
        return int(hid[1:].split(":", 1)[0])
    except Exception:
        return None


def _continuity_signals(candidate: Any, line_obj: Any) -> list[str]:
    text = (getattr(candidate, "text", "") or "").strip()
    signals: list[str] = []
    if text:
        if text[0].isupper():
            signals.append("starts_uppercase")
        if len(text.split()) <= 12:
            signals.append("short_heading_like")
        
        # Handle both dict and object types for line_obj
        def get_attr(obj, key, default=False):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)
        
        # Check both line_obj and candidate for bold/large_font info
        is_bold = bool(get_attr(line_obj, "is_bold", False)) or bool(get_attr(candidate, "is_bold", False))
        is_large_font = bool(get_attr(line_obj, "large_font", False)) or bool(get_attr(candidate, "large_font", False))
        is_mix_bold = bool(get_attr(line_obj, "is_mix_bold", False)) or bool(get_attr(candidate, "is_mix_bold", False))
        
        # FIX: Only add centered signal if explicitly marked as centered in line data
        # Don't infer from candidate object to avoid false positives
        is_centered = bool(get_attr(line_obj, "centered", False)) or bool(get_attr(line_obj, "is_centered", False))
        
        if is_bold:
            signals.append("bold")
        if is_large_font:
            signals.append("large_font")
        if is_centered:
            signals.append("centered")
        if re.match(
            r"^(?:\d+(?:\.\s*\d+)*|[IVXLCDM]+\.|[A-Z]\.|[a-z]\.)\.?\s+",
            text,
            re.IGNORECASE,
        ):
            signals.append("numbered_section")
        if text.endswith(":"):
            signals.append("trailing_colon")
    return signals


def apply_continuity_filter(
    candidates: List[Any],
    layout_by_line_id: Dict[int, Any],
) -> Tuple[List[FinalHeading], List[Dict[str, Any]]]:
    """
    Returns (kept headings, dropped_continuity_log). Same rules as the former inline loop in run_pipeline.
    """
    headings: List[FinalHeading] = []
    dropped_continuity_log: List[Dict[str, Any]] = []

    for c in candidates:
        hid = getattr(c, "id", None) or getattr(c, "heading_id", None)
        lid = parse_line_id_from_heading_id(hid) or getattr(c, "start_line", None) or 0
        line_obj = layout_by_line_id.get(lid)

        # NEW: Check for mixed bold and reject immediately
        def get_attr(obj, key, default=False):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)
        
        is_mix_bold = bool(get_attr(line_obj, "is_mix_bold", False)) or bool(get_attr(c, "is_mix_bold", False))
        if is_mix_bold:
            dropped_continuity_log.append(
                {
                    "heading_id": hid,
                    "text": (getattr(c, "text", "") or "").strip(),
                    "action": "drop_by_continuity",
                    "reason": "continuity_drop(mixed_bold)",
                    "signals_used": [],
                    "line_id": lid,
                }
            )
            continue

        signals = _continuity_signals(c, line_obj)
        text = (getattr(c, "text", "") or "").strip()
        word_count = len(text.split())
        
        # Drop lines ending with function words - these are truncated sentences, not headings
        _trailing_func = re.search(
            r"\b(?:the|a|an|of|in|to|for|with|from|by|at|on|and|or|is|are|was|were|that|which|this|be|has|have|its|their|his|her|it|as)\s*$",
            text, re.IGNORECASE,
        )
        if _trailing_func and "numbered_section" not in signals:
            dropped_continuity_log.append({
                "heading_id": hid, "text": text, "action": "drop_by_continuity",
                "reason": "continuity_drop(ends_with_function_word)", "signals_used": signals, "line_id": lid,
            })
            continue
        
        # Drop lines with hyphenated slug patterns (e.g. "Strict-Liability-What-To-Know-About-It")
        if re.search(r"\b\w+(-\w+){3,}\b", text):
            dropped_continuity_log.append({
                "heading_id": hid, "text": text, "action": "drop_by_continuity",
                "reason": "continuity_drop(hyphen_slug_pattern)", "signals_used": signals, "line_id": lid,
            })
            continue
        
        body_like = (
            word_count >= 14
            or text.endswith(".")
            or "," in text
            or ";" in text
            or (word_count >= 8 and not signals)
        )

        # NEW: If heading has strong layout signals (bold/large_font/centered), don't drop it even with punctuation
        # But be more strict - require bold or large_font, not just centered
        has_strong_layout = any(sig in signals for sig in ("bold", "large_font", "numbered_section"))
        
        # Sentences ending with period are NEVER headings - drop unconditionally regardless of bold
        # Exception: numbered sections (e.g. "1.1 Tort: Definition...") may legitimately end with period
        sentence_glue_words = re.search(r"\b(?:the|and|of|in|to|a|is|that|for|it|as|was|with|on|at|by|be|this|which|or|from|but|not|are)\b", text, re.IGNORECASE)
        if text.endswith(".") and sentence_glue_words and word_count >= 7 and "numbered_section" not in signals:
            dropped_continuity_log.append({
                "heading_id": hid, "text": text, "action": "drop_by_continuity",
                "reason": "continuity_drop(sentence_ends_period)", "signals_used": signals, "line_id": lid,
            })
            continue
        
        # Intro-sentence colons - colon at end AND sentence structure
        # Exception: bold lines ending with ":" are valid headings (author style in legal study materials)
        _colon_intro = (
            text.endswith(":")
            and word_count >= 6
            and "bold" not in signals  # Bold colon endings are intentional headings, not prose intro
            and bool(re.search(
                r"\b(?:are|that|following|follows|include|includes|summarized|listed|noted|stated|discussed"
                r"|remedies|limitations|ways|circumstances|reasons|exceptions|categories|types|principles)\s*:?\s*$"
                r"|\bthe following\b"
                r"|\bfollowing\s+\w+s?\s*:",
                text, re.IGNORECASE,
            ))
        )
        if _colon_intro:
            dropped_continuity_log.append({
                "heading_id": hid, "text": text, "action": "drop_by_continuity",
                "reason": "continuity_drop(intro_sentence_colon)", "signals_used": signals, "line_id": lid,
            })
            continue
        
        # Sentence starters that are clearly prose, not headings
        if re.match(r"^(?:there\s+(?:are|is|were|was|have|has)\b|a\s+person\s+\w+|the\s+above\s+|the\s+following\s+)", text, re.IGNORECASE) and word_count >= 7:
            dropped_continuity_log.append({
                "heading_id": hid, "text": text, "action": "drop_by_continuity",
                "reason": "continuity_drop(prose_sentence_starter)", "signals_used": signals, "line_id": lid,
            })
            continue
        
        # Mid-sentence period: full word (5+ chars) + ". " + uppercase = concatenated sentences
        if re.search(r"\b\w{5,}\. +[A-Z]", text) and word_count >= 8:
            dropped_continuity_log.append({
                "heading_id": hid, "text": text, "action": "drop_by_continuity",
                "reason": "continuity_drop(mid_sentence_period)", "signals_used": signals, "line_id": lid,
            })
            continue
        
        # Dash after "following X" intro phrase
        if re.search(r"\bfollowing\s+\w+s?\s*[-–—]\s*$", text, re.IGNORECASE) and word_count >= 6:
            dropped_continuity_log.append({
                "heading_id": hid, "text": text, "action": "drop_by_continuity",
                "reason": "continuity_drop(following_intro_dash)", "signals_used": signals, "line_id": lid,
            })
            continue
        
        # NEW: Aggressive prose detection for bold lines
        # If line starts with "Illustration," or similar prose indicators, drop it
        prose_indicators = re.match(r"^(?:illustration|example|note|for instance|e\.g\.|i\.e\.|that is|in other words)", text, re.IGNORECASE)
        if prose_indicators and word_count >= 8:
            # This is likely prose content, not a heading
            dropped_continuity_log.append(
                {
                    "heading_id": hid,
                    "text": text,
                    "action": "drop_by_continuity",
                    "reason": "continuity_drop(prose_indicator)",
                    "signals_used": signals,
                    "line_id": lid,
                }
            )
            continue
        
        # NEW: Aggressive sentence structure detection
        # Drop lines with multiple clauses, complex grammar, or sentence-like structure
        complex_sentence_patterns = [
            r"\bwhen\b.*\bthe\b",        # "when the" clauses
            r"\bthat\b.*\bthe\b",        # "that the" clauses
            r"\beach and every\b",       # "each and every" - prose phrase
            r"\bhas a\b.*\bto be\b",     # "has a ... to be" structure
            r"\bsuch\b.*\bare\b",        # "such ... are" structure
            r"\bnot only\b",             # "not only" - additive prose connector
            r"\bmay include\b",          # "may include" - listing prose
            r"\btook place\b",           # past-tense verb phrase
            r"\bdevelopments? took\b",   # past narrative
            r"\bdiscussed on behalf\b",  # narrative verb
            r"\bhave\s+been\b",          # passive voice: "have been ..."
            r"\bhas\s+been\b",           # passive voice: "has been ..."
            r"\bhave\s+been\s+made\b",   # passive: "have been made"
            r"\bis\s+an?\s+organ",       # "is an organisation/organization"
            r"\bmay\s+be\s+committed\b", # "may be committed" - passive
            r"\bmay\s+be\s+made\b",      # "may be made" - passive
        ]
        
        complex_sentence_detected = False
        for pattern in complex_sentence_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                # This has complex sentence structure, likely prose
                complex_sentence_detected = True
                break
        
        if complex_sentence_detected:
            dropped_continuity_log.append(
                {
                    "heading_id": hid,
                    "text": text,
                    "action": "drop_by_continuity",
                    "reason": "continuity_drop(complex_sentence_structure)",
                    "signals_used": signals,
                    "line_id": lid,
                }
            )
            continue
        
        # Drop very long lines that look like prose (even if bold/centered)
        # Numbered sections (e.g. "1.2 Distinction from Crime...") may be longer - allow up to 20 words
        max_heading_words = 20 if "numbered_section" in signals else 15
        if word_count >= max_heading_words:
            # Very long lines are almost always prose, not headings
            dropped_continuity_log.append(
                {
                    "heading_id": hid,
                    "text": text,
                    "action": "drop_by_continuity",
                    "reason": "continuity_drop(too_long_for_heading)",
                    "signals_used": signals,
                    "line_id": lid,
                }
            )
            continue
        
        if body_like and not has_strong_layout:
            dropped_continuity_log.append(
                {
                    "heading_id": hid,
                    "text": text,
                    "action": "drop_by_continuity",
                    "reason": "continuity_drop(body_like_no_heading_signals)",
                    "signals_used": signals,
                    "line_id": lid,
                }
            )
            continue

        if text and not any(sig in signals for sig in ("bold", "large_font", "centered", "numbered_section")):
            low_signal_body = (
                len(text.split()) >= 10
                or text.endswith(".")
                or "," in text
                or ";" in text
                or ":" in text
                or re.search(
                    r"\b(?:which|that|because|therefore|however|whereas|although|since|while|when|where|this|these|those|they|it)\b",
                    text,
                    re.IGNORECASE,
                )
            )
            if low_signal_body:
                dropped_continuity_log.append(
                    {
                        "heading_id": hid,
                        "text": text,
                        "action": "drop_by_continuity",
                        "reason": "continuity_drop(sentence_like_body)",
                        "signals_used": signals,
                        "line_id": lid,
                    }
                )
                continue

        continuity_reason = "continuity_valid(" + ",".join(signals) + ")" if signals else "continuity_valid(no_strong_signals)"
        headings.append(
            FinalHeading(
                id=hid,
                text=getattr(c, "text", ""),
                line_id=int(lid) if isinstance(lid, int) else 0,
                fragment_id=None,
                parent_heading=None,
                reason=continuity_reason,
                signals_used=signals,
                confidence=getattr(c, "confidence", None),
            )
        )

    return headings, dropped_continuity_log

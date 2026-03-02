import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple


QWEN_STRUCTURAL_JUDGE_SYSTEM_PROMPT = """You are a deterministic document structure analysis engine.

You receive structured heading candidates extracted from a PDF document.

Your task is to:

1. Determine whether each candidate is a TRUE STRUCTURAL HEADING.
2. Detect TOC duplicates.
3. Determine hierarchy levels.
4. Assign parent-child relationships.

You must rely ONLY on:
- Title text
- Numbering patterns
- Roman numerals
- Capitalization style
- span_word_count
- span_line_count
- span_preview
- Relative ordering of headings

Do NOT hallucinate.
Do NOT invent headings.
Do NOT modify titles.
Do NOT explain your reasoning.

----------------------------------------
VALIDATION RULES
----------------------------------------

1. If span_word_count is 0 or very small AND the same title appears later with large span → mark this one as:
   - is_valid = false
   - is_toc_duplicate = true

2. Numeric hierarchy:
   - "1" → level 1
   - "1.1" → level 2
   - "1.1.1" → level 3
   - "2.4.3.1" → level 4

3. Roman numerals:
   - "I", "II", "III" → high-level sections
   - Usually level 1 or 2

4. All-caps headings:
   - Likely level 1

5. If span_word_count >= 50:
   - Strong evidence of real heading

6. If title looks like a paragraph sentence:
   - is_valid = false

7. Parent assignment:
   - Parent must be the nearest previous valid heading with lower level.
   - Top-level headings must have parent_id = null.

----------------------------------------
OUTPUT FORMAT (STRICT)
----------------------------------------

Return ONLY valid JSON:

{
  "validated_headings": [
    {
      "id": integer,
      "is_valid": true/false,
      "is_toc_duplicate": true/false,
      "level": integer or null,
      "parent_id": integer or null
    }
  ]
}

Do not add explanations.
Do not add extra keys.
Do not output text outside JSON.
"""


@dataclass(frozen=True)
class StructuralJudgeConfig:
    qwen_runner: str = "scripts/run_qwen_local.py"
    temperature: float = 0.0
    top_p: float = 1.0
    max_preview_words: int = 500
    toc_small_span_words: int = 10  # used by deterministic fallback duplicate detection
    fallback_min_words: int = 40


def _words(text: str) -> List[str]:
    return re.findall(r"\w+(?:'\w+)?", text)


def make_span_preview(span_lines: List[str], max_words: int = 500) -> str:
    """
    Create a compact preview from span lines capped by word count.
    Intended for LLM input: first ~400-600 words.
    """
    if not span_lines:
        return ""
    out_words: List[str] = []
    for ln in span_lines:
        ws = _words(ln)
        if not ws:
            continue
        remaining = max_words - len(out_words)
        if remaining <= 0:
            break
        out_words.extend(ws[:remaining])
    return " ".join(out_words)


def build_judge_payload(
    document_title: str,
    spans: List[Dict[str, Any]],
    lines: Optional[List[str]] = None,
    config: Optional[StructuralJudgeConfig] = None,
) -> Dict[str, Any]:
    """
    Converts spans into the strict JSON schema to send to Qwen.

    Expected span fields:
      - start_index, end_index, span_word_count, span_line_count
      - title (string)

    If `lines` is provided, span_preview is derived from lines[start_index+1:end_index+1].
    Otherwise, span_preview is empty.
    """
    cfg = config or StructuralJudgeConfig()
    headings = []
    for i, s in enumerate(spans, start=1):
        start = int(s.get("start_index", 0))
        end = int(s.get("end_index", start))
        span_lines = []
        if lines is not None:
            span_lines = lines[start + 1 : end + 1]
        preview = make_span_preview(span_lines, max_words=cfg.max_preview_words)

        headings.append(
            {
                "id": i,
                "index": int(s.get("start_index", s.get("index", 0))),
                "title": str(s.get("title", "")).strip(),
                "span_word_count": int(s.get("span_word_count", 0)),
                "span_line_count": int(s.get("span_line_count", 0)),
                "span_preview": preview,
            }
        )

    return {"document_title": document_title, "headings": headings}


def _extract_json_object(text: str) -> Optional[str]:
    """
    Best-effort extraction of the first top-level JSON object from raw model output.
    This helps when the model accidentally prefixes/suffixes whitespace or tokens.
    """
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def call_qwen_structural_judge(
    payload: Dict[str, Any],
    config: Optional[StructuralJudgeConfig] = None,
    system_prompt: str = QWEN_STRUCTURAL_JUDGE_SYSTEM_PROMPT,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Calls local Qwen via the existing runner script.

    Returns: (parsed_json_or_None, raw_output)
    """
    cfg = config or StructuralJudgeConfig()

    full_prompt = (
        f"<|system|>\n{system_prompt}\n"
        f"<|user|>\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        f"<|assistant|>"
    )

    # Note: we can't guarantee runner accepts temp/top_p as args;
    # those should be set inside run_qwen_local.py as per your setup.
    proc = subprocess.run(
        ["python", cfg.qwen_runner],
        input=full_prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )

    raw = (proc.stdout or "").strip()

    # Try strict parse first, then best-effort extraction
    try:
        return json.loads(raw), raw
    except Exception:
        extracted = _extract_json_object(raw)
        if extracted:
            try:
                return json.loads(extracted), raw
            except Exception:
                pass
    return None, raw


def validate_structural_output(
    model_output: Dict[str, Any],
    payload: Dict[str, Any],
) -> Tuple[bool, str]:
    """
    Strict validation. If anything fails -> return (False, reason).
    """
    if not isinstance(model_output, dict):
        return False, "output_not_object"

    if "validated_headings" not in model_output:
        return False, "missing_validated_headings"

    validated = model_output["validated_headings"]
    if not isinstance(validated, list):
        return False, "validated_headings_not_list"

    input_ids: Set[int] = set()
    for h in payload.get("headings", []):
        try:
            input_ids.add(int(h["id"]))
        except Exception:
            return False, "input_payload_bad_ids"

    required_keys = {"id", "is_valid", "is_toc_duplicate", "level", "parent_id"}

    seen_ids: Set[int] = set()
    id_to_level: Dict[int, Optional[int]] = {}
    id_to_is_valid: Dict[int, bool] = {}
    parent_map: Dict[int, Optional[int]] = {}

    for item in validated:
        if not isinstance(item, dict):
            return False, "item_not_object"

        if set(item.keys()) != required_keys:
            return False, "unexpected_or_missing_keys"

        # id
        if not isinstance(item["id"], int):
            return False, "id_not_int"
        hid = item["id"]
        if hid not in input_ids:
            return False, "id_not_in_input"
        if hid in seen_ids:
            return False, "duplicate_id"
        seen_ids.add(hid)

        # booleans
        if not isinstance(item["is_valid"], bool):
            return False, "is_valid_not_bool"
        if not isinstance(item["is_toc_duplicate"], bool):
            return False, "is_toc_duplicate_not_bool"

        # level
        lvl = item["level"]
        if lvl is not None:
            if not isinstance(lvl, int) or lvl <= 0:
                return False, "level_invalid"

        # parent_id
        pid = item["parent_id"]
        if pid is not None:
            if not isinstance(pid, int):
                return False, "parent_id_not_int"
            if pid == hid:
                return False, "self_parenting"
            if pid not in input_ids:
                return False, "parent_id_not_in_input"

        id_to_level[hid] = lvl
        id_to_is_valid[hid] = item["is_valid"]
        parent_map[hid] = pid

    # All ids must be present exactly once (strict contract)
    if seen_ids != input_ids:
        return False, "missing_some_ids_in_output"

    # Parent must reference another VALID id (or null)
    for hid, pid in parent_map.items():
        if pid is None:
            continue
        if not id_to_is_valid.get(pid, False):
            return False, "parent_not_valid"

    # Parent level must be lower (numerically smaller) than child level.
    for hid, pid in parent_map.items():
        if pid is None:
            continue
        child_lvl = id_to_level.get(hid)
        parent_lvl = id_to_level.get(pid)
        # if either level is null, invalid relationship
        if child_lvl is None or parent_lvl is None:
            return False, "null_level_in_parent_chain"
        if not (parent_lvl < child_lvl):
            return False, "parent_level_not_lower"

    return True, "ok"


_NUM_PREFIX_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\b")
_ROMAN_RE = re.compile(r"^\s*([IVXLCDM]+)\b", re.IGNORECASE)


def infer_level_from_title(title: str) -> Optional[int]:
    """
    Deterministic level inference:
    - Numeric "1" => 1, "1.2" => 2, "1.2.3" => 3
    - Roman => 1 (conservative)
    - ALL CAPS short-ish => 1
    - otherwise None
    """
    t = (title or "").strip()

    m = _NUM_PREFIX_RE.match(t)
    if m:
        parts = m.group(1).split(".")
        return len(parts)

    m = _ROMAN_RE.match(t)
    if m and re.match(r"^[IVXLCDM]+", m.group(1), re.IGNORECASE):
        return 1

    letters = re.findall(r"[A-Za-z]", t)
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / max(1, len(letters))
        if upper_ratio > 0.9 and len(t) <= 80:
            return 1

    return None


def _canonical_title(title: str) -> str:
    """
    Canonical title for duplicate detection.
    - collapse whitespace
    - lowercase
    """
    t = (title or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def deterministic_fallback(
    payload: Dict[str, Any],
    config: Optional[StructuralJudgeConfig] = None,
) -> Dict[str, Any]:
    """
    Deterministic fallback when LLM output fails validation.

    Rules:
    - Keep headings with span_word_count >= fallback_min_words OR numeric/roman inferred level
    - Remove duplicates by keeping larger span_word_count for same canonical title
    - Determine levels via numbering patterns where possible
    - Assign parent as closest previous valid heading with lower level (or numeric prefix parent)
    """
    cfg = config or StructuralJudgeConfig()
    headings: List[Dict[str, Any]] = payload.get("headings", [])
    id_to_heading = {int(h["id"]): h for h in headings}

    # Mark preliminary validity and compute inferred level.
    prelim: Dict[int, Dict[str, Any]] = {}
    for hid, h in id_to_heading.items():
        title = str(h.get("title", "")).strip()
        wc = int(h.get("span_word_count", 0))
        inferred_level = infer_level_from_title(title)

        is_valid = bool(inferred_level is not None or wc >= cfg.fallback_min_words)

        prelim[hid] = {
            "id": hid,
            "title": title,
            "index": int(h.get("index", 0)),
            "span_word_count": wc,
            "level": inferred_level,
            "is_valid": is_valid,
            "is_toc_duplicate": False,
            "parent_id": None,
        }

    # Duplicate removal by canonical title: keep the one with larger span_word_count.
    title_to_best: Dict[str, int] = {}
    for hid, item in sorted(prelim.items(), key=lambda kv: kv[1]["index"]):
        key = _canonical_title(item["title"])
        if key not in title_to_best:
            title_to_best[key] = hid
            continue

        best_id = title_to_best[key]
        best = prelim[best_id]
        cur = item

        # Determine which is real: prefer larger span
        if cur["span_word_count"] > best["span_word_count"]:
            # Mark previous as TOC duplicate if it is tiny
            if best["span_word_count"] <= cfg.toc_small_span_words:
                best["is_valid"] = False
                best["is_toc_duplicate"] = True
            title_to_best[key] = hid
        else:
            if cur["span_word_count"] <= cfg.toc_small_span_words:
                cur["is_valid"] = False
                cur["is_toc_duplicate"] = True

    # If a heading is invalid but not marked duplicate, keep it invalid.
    # Ensure levels for valid headings:
    for item in prelim.values():
        if item["is_valid"] and item["level"] is None:
            # non-numeric valid due to content: assign as level of previous + 1 (best-effort),
            # but cap at 6; if no previous, make it level 1.
            item["level"] = 1

    # Parent assignment by nearest previous valid heading with lower level.
    ordered = sorted(prelim.values(), key=lambda x: x["index"])
    valid_stack: List[Dict[str, Any]] = []
    for item in ordered:
        if not item["is_valid"]:
            continue

        lvl = int(item["level"])
        while valid_stack and int(valid_stack[-1]["level"]) >= lvl:
            valid_stack.pop()
        item["parent_id"] = valid_stack[-1]["id"] if valid_stack else None
        valid_stack.append(item)

    # Emit in required schema order, include all ids
    validated_headings = []
    for hid in sorted(prelim.keys()):
        item = prelim[hid]
        validated_headings.append(
            {
                "id": hid,
                "is_valid": bool(item["is_valid"]),
                "is_toc_duplicate": bool(item["is_toc_duplicate"]),
                "level": int(item["level"]) if item["is_valid"] and item["level"] is not None else None,
                "parent_id": int(item["parent_id"]) if item["is_valid"] and item["parent_id"] is not None else None,
            }
        )

    return {"validated_headings": validated_headings}


def run_structural_judge(
    payload: Dict[str, Any],
    config: Optional[StructuralJudgeConfig] = None,
) -> Dict[str, Any]:
    """
    Full judge pipeline:
    - call Qwen
    - validate output
    - fallback if needed
    """
    cfg = config or StructuralJudgeConfig()
    parsed, raw = call_qwen_structural_judge(payload, cfg)
    if parsed is not None:
        ok, _reason = validate_structural_output(parsed, payload)
        if ok:
            return parsed

    # fallback
    return deterministic_fallback(payload, cfg)

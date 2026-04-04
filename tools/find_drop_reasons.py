import glob
import json
import os

TARGETS = [
    "LAW OF TORTS, MOTOR ACCIDENT CLAIMS AND CONSUMER PROTECTION",
    "MODULE 1:",
]

STAGE_FILES = [
    "03_candidate_scoring.json",
    "03b_pre_llm_heading_gate.json",
    "08b_continuity_filter.json",
    "09_final_headings.json",
]


def main() -> None:
    runs = sorted(glob.glob("logs/run_*"), reverse=True)
    print("runs", len(runs))
    if not runs:
        return
    run_dir = runs[0]
    print("run_dir", run_dir)

    for sf in STAGE_FILES:
        path = os.path.join(run_dir, sf)
        if not os.path.exists(path):
            print("missing", sf)
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print("stage", sf, "items", len(data) if isinstance(data, list) else type(data).__name__)

        if not isinstance(data, list):
            continue

        for it in data:
            if not isinstance(it, dict):
                continue
            tx = str(it.get("text") or "")
            low = tx.lower()
            if any(t.lower() in low for t in TARGETS):
                out = {}
                for k in [
                    "line_id",
                    "heading_id",
                    "score",
                    "selected",
                    "action",
                    "reason",
                    "signals",
                    "signals_used",
                    "page_number",
                    "text",
                ]:
                    if k in it:
                        out[k] = it.get(k)
                print("  MATCH", sf, out)


if __name__ == "__main__":
    main()

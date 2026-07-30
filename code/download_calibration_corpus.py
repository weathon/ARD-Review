"""
Build the calibration corpus from the public DeepReview-13K dataset.

Writes datasets/deepreview_13k_calibration/<paper_id>.md — one markdown file per
paper (title, decision, avg score, `- Scores:` line, abstract, all human
reviews). This is the corpus the merger's calibration_search retrieves anchor
papers from.

The matching embedding matrix and avg-score index are NOT built here: they are
downloaded from HuggingFace (weathon/paper_embeddings) on first use by
paths.ensure_hf_file, so the file names in this directory must stay exactly
"<paper_id>.md" as written below.

Usage:  python code/download_calibration_corpus.py
"""

import json

import tqdm
from datasets import load_dataset

from paths import DATASETS_DIR

CAL_DIR = (DATASETS_DIR / "deepreview_13k_calibration").resolve()

REVIEW_FIELDS = [
    "summary",
    "strengths",
    "weaknesses",
    "questions",
    "limitations",
    "soundness",
    "presentation",
    "contribution",
    "rating",
    "confidence",
]


def extract_title(user_content: str) -> str:
    marker = r"\title{"
    if marker in user_content:
        start = user_content.index(marker) + len(marker)
        depth = 1
        i = start
        while i < len(user_content) and depth > 0:
            ch = user_content[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return user_content[start:i].strip().replace("\n", " ")
            i += 1
    return ""


def extract_abstract(user_content: str) -> str:
    open_marker = r"\begin{abstract}"
    close_marker = r"\end{abstract}"
    if open_marker in user_content and close_marker in user_content:
        a = user_content.index(open_marker) + len(open_marker)
        b = user_content.index(close_marker)
        return user_content[a:b].strip()
    return ""


# NOTE: the field access below (and the tolerant JSON parse in main()) is kept
# byte-for-byte equivalent to the script that generated the corpus the published
# embeddings/score-index were computed from. Changing how a malformed or partial
# DeepReview row is rendered would produce files that no longer match the
# HuggingFace embedding matrix, silently degrading retrieval.
def first_user_content(inputs_json: str) -> str:
    msgs = json.loads(inputs_json)
    for m in msgs:
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


def format_human_reviews_md(reviewer_comments: list[dict]) -> str:
    sections = []
    for i, rc in enumerate(reviewer_comments, start=1):
        content = rc.get("content", {}) or {}
        rating = rc.get("rating", content.get("rating", ""))
        confidence = content.get("confidence", "")
        parts = [f"## Human Reviewer {i}"]
        if rating != "":
            parts.append(f"### Rating\n{rating}")
            parts.append(f"### Rating Number\n{rating}")
        if confidence != "":
            parts.append(f"### Confidence\n{confidence}")
        for field in REVIEW_FIELDS:
            if field in ("rating", "confidence"):
                continue
            v = content.get(field, "")
            if v in ("", None):
                continue
            parts.append(f"### {field.replace('_',' ').title()}\n{v}")
        sections.append("\n\n".join(parts))
    return "\n\n---\n\n".join(sections)


def coerce_scores(raw) -> list[int]:
    """DeepReview-13K stores ratings either as ints or as '<score>: <label>' strings."""
    out: list[int] = []
    if not raw:
        return out
    if isinstance(raw, str):
        raw = json.loads(raw)
    for s in raw:
        try:
            if isinstance(s, str):
                out.append(int(s.split(":", 1)[0].strip()))
            else:
                out.append(int(s))
        except (ValueError, TypeError):
            continue
    return out


def main():
    print("Loading WestlakeNLP/DeepReview-13K ...")
    ds = load_dataset("WestlakeNLP/DeepReview-13K")
    train = ds["train"]

    CAL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing calibration corpus to {CAL_DIR} ({len(train)} papers) ...")
    written = 0
    for ex in tqdm.tqdm(train):
        pid = ex["id"]
        scores = coerce_scores(ex["rating"])
        if not scores:
            continue
        avg = sum(scores) / len(scores)
        user_content = first_user_content(ex["inputs"])
        title = extract_title(user_content) or pid
        try:
            reviewer_comments = json.loads(ex["reviewer_comments"]) if ex["reviewer_comments"] else []
        except json.JSONDecodeError:
            reviewer_comments = []
        md = "\n".join([
            f"# {title}",
            "",
            f"- Decision: {ex['decision'] or ''}",
            f"- Avg Score: {avg:.2f}",
            f"- Scores: {', '.join(str(s) for s in scores)}",
            "",
            "## Abstract",
            extract_abstract(user_content),
            "",
            "## Human Reviews",
            "",
            format_human_reviews_md(reviewer_comments),
        ]).strip() + "\n"
        (CAL_DIR / f"{pid}.md").write_text(md, encoding="utf-8")
        written += 1
    print(f"Done — wrote {written} calibration files to {CAL_DIR}")


if __name__ == "__main__":
    main()

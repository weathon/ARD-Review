"""Function tools for the OpenAI Agents SDK path: file access + calibration RAG.

The calibration corpus is a directory of human-review markdown files (one per
paper, each carrying a `- Scores:` line). It is NOT shipped with this release —
build it with `code/download_calibration_corpus.py`, which writes
`datasets/deepreview_13k_calibration/` from the public DeepReview-13K dataset.
The embedding matrix and the per-file avg-score index are downloaded from
HuggingFace on first use (see paths.ensure_hf_file).
"""
from agents import function_tool
import os

from paths import DATASETS_DIR, ensure_hf_file

CALIBRATION_REVIEW_DIR = str((DATASETS_DIR / "deepreview_13k_calibration").resolve())

# ── Model/provider configuration (default: OpenRouter) ───────────────
API_BASE_URL = os.environ.get("REVIEW_API_BASE_URL", "https://openrouter.ai/api/v1")
EMBEDDING_MODEL = os.environ.get("REVIEW_EMBEDDING_MODEL", "google/gemini-embedding-001")

import dotenv
dotenv.load_dotenv()
API_KEY = os.environ["REVIEW_API_KEY"]

ALLOWED_PATHS = [CALIBRATION_REVIEW_DIR]

from rank_bm25 import BM25Okapi
from openai import OpenAI
import numpy as np
import pickle
import sys
import time

embed_client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

# ── Build index ──────────────────────────────────────────────────────
# With --no_cal the merger has no calibration_search tool, so neither the corpus
# nor the embedding matrix is needed and we skip the whole indexing step.
NO_CAL = "--no_cal" in sys.argv
database = {}
filenames: list[str] = []
vectors = None
score_index: dict[str, float] = {}

if not NO_CAL:
    if not os.path.isdir(CALIBRATION_REVIEW_DIR):
        raise FileNotFoundError(
            f"Calibration corpus not found at {CALIBRATION_REVIEW_DIR}. "
            "Run `python code/download_calibration_corpus.py` first, or pass --no_cal "
            "to score without calibration anchors."
        )
    print(f"Indexing calibration corpus from {CALIBRATION_REVIEW_DIR} ...")
    start = time.time()
    for path in ALLOWED_PATHS:
        all_files = []
        all_file_paths = []
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith(".txt") or file.endswith(".md"):
                    with open(os.path.join(root, file), "r", errors="replace") as f:
                        all_files.append(f.read())
                        all_file_paths.append(os.path.join(root, file))

        tokenized_corpus = [doc.split(" ") for doc in all_files if doc.strip()]
        if not tokenized_corpus:
            raise RuntimeError(f"No calibration review files found under {path}")
        bm25 = BM25Okapi(tokenized_corpus)
        database[path] = {"files": all_file_paths, "bm25": bm25}

    print("Indexing complete. Time taken: {:.2f}s".format(time.time() - start))

    with open(ensure_hf_file("human_reviews_embeddings_deepreview.pkl"), "rb") as f:
        db = pickle.load(f)
    filenames = list(db.keys())
    vectors = np.array(list(db.values()))

    # Per-file avg human score (basename -> float). Used to pre-filter candidates
    # by score range before BM25/vector ranking.
    with open(ensure_hf_file("human_review_score_index_deepreview.pkl"), "rb") as f:
        score_index = pickle.load(f)


# ── Tools ────────────────────────────────────────────────────────────
def allow_path(path: str):
    """Extend ALLOWED_PATHS at runtime (e.g. to grant the merger access to the paper_dir)."""
    resolved = os.path.abspath(path)
    if resolved not in ALLOWED_PATHS:
        ALLOWED_PATHS.append(resolved)


@function_tool
def read_file(abs_path: str, start_line: int = 1, end_line: int = 0) -> str:
    """Read lines from a file. Returns lines numbered start_line to end_line (inclusive, 1-based).
    By default (start_line=1, end_line=0), reads the entire file. Only pass start_line/end_line
    when you specifically need a partial slice; the default is to read the whole file.
    If access is denied, only re-check whether the requested path is misspelled; do not explore
    directories or try nearby paths."""
    resolved = os.path.abspath(abs_path)
    print(f"  [read_file] Request to read '{resolved}' lines {start_line} to {end_line if end_line > 0 else 'EOF'}")
    if not any(resolved.startswith(ap) for ap in ALLOWED_PATHS):
        print(f"  [read_file] BLOCKED: '{resolved}' is not under any allowed directory.")
        return f"ERROR: Access denied. Path '{resolved}' is not under any allowed directory. The agent may access only the specific allowed paths. Do not explore directories or nearby paths; only double-check whether the requested path was misspelled."
    with open(abs_path, "r") as f:
        lines = f.readlines()
    selected = lines[max(0, start_line - 1):end_line if end_line > 0 else len(lines)]
    return "".join(f"{start_line + i}: {line}" for i, line in enumerate(selected))


@function_tool
def grep_file(pattern: str, abs_path: str) -> str:
    """Search a single file for a pattern. Returns matching lines with line numbers.
    If access is denied, only re-check whether the requested path is misspelled; do not explore
    directories or try nearby paths."""
    import re
    resolved = os.path.abspath(abs_path)
    print(f"  [grep_file] Request to grep for pattern '{pattern}' in '{resolved}'")
    if not any(resolved.startswith(ap) for ap in ALLOWED_PATHS):
        print(f"  [grep_file] BLOCKED: '{resolved}' is not under any allowed directory.")
        return f"ERROR: Access denied. Path '{resolved}' is not under any allowed directory. The agent may access only the specific allowed paths. Do not explore directories or nearby paths; only double-check whether the requested path was misspelled."
    if not os.path.isfile(resolved):
        return f"ERROR: '{resolved}' is not a file. Do not explore directories or nearby paths; only double-check whether the requested path was misspelled."
    matches = []
    with open(resolved, "r", errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            if re.search(pattern, line):
                matches.append(f"{i}: {line.rstrip()}")
    return "\n".join(matches) if matches else "No matches found."


def search_file_impl(query: str, n: int, mode: str, low_score: float = -1.0, high_score: float = 11.0) -> str:
    """Search the calibration corpus, filtered by the reviewer avg-score range.

    Args:
        query: search query.
        n: number of top results.
        mode: 'vector' for semantic similarity, 'bm25' for keyword matching.
        low_score: include only papers with avg score > low_score (default -1.0).
        high_score: include only papers with avg score < high_score (default 11.0).

    Filtering is applied FIRST by score range, THEN ranking (BM25/vector) runs
    over the filtered subset. Use this to anchor calibration to a specific
    score band (e.g. low_score=7, high_score=10 for strong papers).
    """
    print(f"  [search_file] query='{query}' mode='{mode}' n={n} score=({low_score}, {high_score})")
    if mode == "bm25":
        bm25 = list(database.values())[0]["bm25"]
        files = list(database.values())[0]["files"]
        allowed_idx = [
            i for i, p in enumerate(files)
            if low_score < score_index[os.path.basename(p)] < high_score
        ]
        if not allowed_idx:
            return "No files in that score range."
        tokenized_query = query.split(" ")
        doc_scores = bm25.get_scores(tokenized_query)
        allowed_sorted = sorted(allowed_idx, key=lambda i: doc_scores[i], reverse=True)[:n]
        results = []
        for idx in allowed_sorted:
            file_path = os.path.abspath(files[idx])
            rel = doc_scores[idx]
            avg = score_index[os.path.basename(file_path)]
            with open(file_path, 'r', errors='replace') as f:
                content = f.read()
            results.append(f"{file_path}\navg_score: {avg:.2f}  bm25: {rel:.2f}\n first 1000 chars:\n{content[:1000]}\n")
        return "\n---\n".join(results) if results else "No relevant files found."
    elif mode == "vector":
        allowed_mask = np.array([
            low_score < score_index[fn] < high_score for fn in filenames
        ])
        if not allowed_mask.any():
            return "No files in that score range."
        query_embedding = embed_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=query,
            encoding_format="float"
        )
        query_vector = np.array(query_embedding.data[0].embedding)
        similarities = vectors @ query_vector.T
        masked = np.where(allowed_mask, similarities, -np.inf)
        top_indices = masked.argsort()[-n:][::-1]
        results = []
        for idx in top_indices:
            if not np.isfinite(masked[idx]):
                break
            fn = filenames[idx]
            file_path = os.path.abspath(os.path.join(CALIBRATION_REVIEW_DIR, fn))
            rel = similarities[idx]
            avg = score_index[fn]
            with open(file_path, "r", errors="replace") as file_handle:
                content = file_handle.read()
            results.append(f"{file_path}\navg_score: {avg:.2f}  sim: {rel:.2f}\n first 1000 chars:\n{content[:1000]}\n")
        return "\n---\n".join(results) if results else "No relevant files found."
    else:
        return "ERROR: Invalid search mode. Use 'bm25' or 'vector'."

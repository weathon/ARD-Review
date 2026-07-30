"""Centralized path resolution.

Layout (defaults):
  <repo_root>/
    code/        # this file lives here
    prompts/
    datasets/    # calibration review corpus, embeddings .pkl, score_index .pkl
    results/     # calibration CSVs shipped with the release + run outputs

Override via env vars:
  REVIEW_REPO_ROOT      — repo root (defaults to parent of this file's dir)
  REVIEW_PROMPTS_DIR    — prompts dir (default <root>/prompts)
  REVIEW_DATASETS_DIR   — datasets dir (default <root>/datasets)
  REVIEW_RESULTS_DIR    — results dir (default <root>/results)
"""
from __future__ import annotations
import os
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("REVIEW_REPO_ROOT", _THIS_DIR.parent)).resolve()
PROMPTS_DIR = Path(os.environ.get("REVIEW_PROMPTS_DIR", REPO_ROOT / "prompts")).resolve()
DATASETS_DIR = Path(os.environ.get("REVIEW_DATASETS_DIR", REPO_ROOT / "datasets")).resolve()
RESULTS_DIR = Path(os.environ.get("REVIEW_RESULTS_DIR", REPO_ROOT / "results")).resolve()


def prompt_path(name: str) -> str:
    return str(PROMPTS_DIR / name)


def dataset_path(name: str) -> str:
    return str(DATASETS_DIR / name)


def results_path(name: str) -> str:
    return str(RESULTS_DIR / name)


# Embeddings/score-index pickles are hosted on HuggingFace (public repo, plain
# HTTPS — no `huggingface_hub` library needed). On first access we stream the
# file into DATASETS_DIR.
HF_REPO = os.environ.get("REVIEW_HF_REPO", "weathon/paper_embeddings")
HF_BASE = f"https://huggingface.co/datasets/{HF_REPO}/resolve/main"


def ensure_hf_file(name: str) -> str:
    """Return local path to `name`, downloading from the HF repo if missing."""
    import urllib.request
    import shutil

    local = DATASETS_DIR / name
    if local.exists():
        return str(local)
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    url = f"{HF_BASE}/{name}"
    tmp = local.with_suffix(local.suffix + ".part")
    print(f"[paths] downloading {url} -> {local}")
    with urllib.request.urlopen(url) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out, length=1 << 20)
    tmp.rename(local)
    return str(local)

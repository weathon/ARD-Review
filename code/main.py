"""
ARD-Review: two-stage agentic paper reviewer.

  Phase 1  Harsh Critic — reads the paper from disk in chunks, reasons through it
           incrementally, and produces a critical review.
  Phase 2  Merger — cross-checks every weakness against the paper, retrieves
           human-reviewed anchor papers from the calibration corpus (iterative
           RAG, up to 3 batched queries), and writes the final review with
           <score> and <decision> tags.

Both stages run either on the OpenAI Agents SDK (any OpenAI-compatible endpoint;
default OpenRouter) or on the Claude Agent SDK (model id prefixed 'claude_sdk:').

Configuration is entirely via environment variables — see README.md.
"""
import argparse
import asyncio
import csv
import os
import re
import sys
import time
from pathlib import Path

import dotenv
dotenv.load_dotenv()

from pydantic import BaseModel

from paths import prompt_path, RESULTS_DIR
from tools import (
    API_BASE_URL,
    API_KEY,
    CALIBRATION_REVIEW_DIR,
    allow_path,
    grep_file,
    read_file,
    search_file_impl,
)

from agents import Agent, OpenAIResponsesModel, Runner, function_tool, set_default_openai_client, set_tracing_disabled
from agents.model_settings import ModelSettings
from openai import AsyncOpenAI

api_client = AsyncOpenAI(base_url=API_BASE_URL, api_key=API_KEY)
set_default_openai_client(api_client)
set_tracing_disabled(True)

# Reasoning effort is passed through as extra_body. OPENROUTER_PROVIDER pins the
# upstream provider (OpenRouter only) so a run cannot silently switch backends.
REASONING_EFFORT = os.environ["REASONING_EFFORT"]
OPENROUTER_PROVIDER = os.environ.get("OPENROUTER_PROVIDER", "")
_extra_body = {"effort": REASONING_EFFORT}
if OPENROUTER_PROVIDER:
    _extra_body["provider"] = {"only": [OPENROUTER_PROVIDER]}
MODEL_SETTINGS = ModelSettings(extra_body=_extra_body)

HARSH_MODEL = os.environ["HARSH_MODEL"]
MERGER_MODEL = os.environ["MERGER_MODEL"]
# Used only when the merger's own <score>/<decision> tags cannot be parsed.
EXTRACTOR_MODEL = os.environ["EXTRACTOR_MODEL"]

HUMAN_REVIEW_DIR = CALIBRATION_REVIEW_DIR

# ── Agent-level retry ────────────────────────────────────────────────
MAX_RETRIES = 5
RETRY_DELAY = 10


async def run_agent_with_retry(agent, prompt: str, max_turns: int = 30) -> tuple[str, object]:
    agent_name = agent.name
    print(f"  [{agent_name}] starting ...")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await Runner.run(agent, prompt, max_turns=max_turns)
            output = result.final_output
            if not output or not output.strip():
                if attempt < MAX_RETRIES:
                    print(f"  [{agent_name}] empty response (attempt {attempt}/{MAX_RETRIES}), retrying ...")
                    await asyncio.sleep(RETRY_DELAY + attempt * 5)
                    continue
                raise RuntimeError(f"[{agent_name}] empty response after {MAX_RETRIES} attempts")
            print(f"  [{agent_name}] done")
            return output, result.context_wrapper.usage
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = RETRY_DELAY * attempt
                print(f"  [{agent_name}] error (attempt {attempt}/{MAX_RETRIES}), waiting {wait}s ... {e}")
                await asyncio.sleep(wait)
            else:
                raise RuntimeError(f"[{agent_name}] {e}") from e
    raise RuntimeError(f"[{agent_name}] failed after {MAX_RETRIES} attempts")


# ── Prompt loading ───────────────────────────────────────────────────
with open(prompt_path("timeline.md"), "r") as f:
    timeline = f.read().replace("{{CURRENT_DATE}}", time.strftime("%Y-%m-%d"))

PAPER_ACCESS_FILE = "The paper path is provided in the user message. Use read_file to read the paper (it reads the whole file by default — do not pass start_line/end_line unless you specifically need a slice) and verify reviewer claims directly."
PAPER_ACCESS_CHUNKED = """The paper path is provided in the user message. The paper is NOT included inline — read it from disk in sequential chunks using read_file with start_line/end_line, and use grep_file to locate specific claims or sections.

Read the paper progressively, one chunk at a time. After each chunk, before reading the next one, pause and reason: think through what this part of the paper claims, whether the method/evidence/argument in it holds up, and note any concerns or strengths it surfaces. Build your assessment incrementally as you go — do not dump the whole paper into context and review it all at the end. Only move to the next chunk once you have thought through the current one. Choose reasonable chunk sizes (e.g. a section or a few hundred lines at a time)."""

with open(prompt_path("cal_with.md"), "r") as _f:
    CAL_INSTRUCTION_WITH = _f.read()

with open(prompt_path("cal_without.md"), "r") as _f:
    CAL_INSTRUCTION_WITHOUT = _f.read()


def load_prompts(path, paper_access: str, no_cal: bool):
    with open(prompt_path(path), "r") as f:
        raw_lines = f.readlines()
    kept_lines = []
    for lineno, line in enumerate(raw_lines, start=1):
        if line.lstrip().startswith("&&"):
            print(f"WARNING: ignoring commented line {lineno} in prompts/{path}: {line.rstrip()}")
            continue
        kept_lines.append(line)
    content = "".join(kept_lines)
    content = content.replace("{{PAPER_ACCESS_INSTRUCTION}}", paper_access)
    cal_instruction = CAL_INSTRUCTION_WITHOUT if no_cal else CAL_INSTRUCTION_WITH
    content = content.replace("{{CALIBRATION_INSTRUCTION}}", cal_instruction)
    return content + "\n\n" + timeline


# ── Agent definitions ────────────────────────────────────────────────
NO_CAL = "--no_cal" in sys.argv

if HARSH_MODEL.startswith("claude_sdk:"):
    harsh = None  # Claude SDK Harsh Critic — invoked per-call in run_pipeline
    HARSH_SDK_MODEL = HARSH_MODEL[len("claude_sdk:"):]
    harsh_sdk_system_prompt = load_prompts("harsh_critic.md", paper_access=PAPER_ACCESS_FILE, no_cal=True)
else:
    harsh = Agent(
        name="Harsh Critic",
        instructions=load_prompts("harsh_critic.md", paper_access=PAPER_ACCESS_CHUNKED, no_cal=True),
        model=OpenAIResponsesModel(model=HARSH_MODEL, openai_client=api_client),
        tools=[read_file, grep_file],
        model_settings=MODEL_SETTINGS,
    )
    HARSH_SDK_MODEL = None
    harsh_sdk_system_prompt = None

if MERGER_MODEL.startswith("claude_sdk:"):
    merger = None  # Claude SDK merger — created per-call in run_pipeline
    MERGER_SDK_MODEL = MERGER_MODEL[len("claude_sdk:"):]
else:
    @function_tool
    def draft_review(draft: str) -> str:
        """Record the merger's post-filtering draft before calibration or final writing."""
        return "draft recorded"

    if NO_CAL:
        merger_tools = [read_file, grep_file, draft_review]
    else:
        class CalibrationQuery(BaseModel):
            query: str
            n: int = 4
            low_score: float = -1.0
            high_score: float = 11.0

        @function_tool
        def calibration_search(queries: list[CalibrationQuery]) -> str:
            """RAG retrieval over the human-review corpus.

            Pass a batch of queries; each runs vector search and returns top-n
            hits with avg human score and first 1000 chars. Up to 3 calls
            total across the session (bracket -> narrow -> optional re-narrow);
            see the calibration protocol in the system prompt for when to use
            each round.

            Args:
                queries: list of {query: str, n?: int, low_score?: float,
                    high_score?: float}.
            """
            if not isinstance(queries, list) or not queries:
                raise ValueError("calibration_search: 'queries' must be a non-empty list of query objects.")
            sections = []
            for i, q in enumerate(queries, 1):
                body = search_file_impl(q.query, q.n, "vector", q.low_score, q.high_score)
                sections.append(
                    f"### Query {i}: {q.query!r}  (n={q.n}, score=({q.low_score}, {q.high_score}))\n{body}"
                )
            return "\n\n".join(sections)

        merger_tools = [read_file, grep_file, draft_review, calibration_search]

    merger = Agent(
        name="Merger",
        instructions=load_prompts("merger.md", paper_access=PAPER_ACCESS_FILE, no_cal=NO_CAL),
        model=OpenAIResponsesModel(model=MERGER_MODEL, openai_client=api_client),
        tools=merger_tools,
        model_settings=MODEL_SETTINGS,
    )
    MERGER_SDK_MODEL = None


REVIEW_PROMPT = """Review the following paper thoroughly.

The paper was extracted from PDF by an automated parser. Treat formatting artifacts (broken equations, garbled tables, OCR errors) as parser issues, not paper flaws. The appendix and references were stripped by the parser; assume they exist in the original submission and don't flag them as missing.

Paper path: {paper_path}. The paper is not included inline — read it from disk in chunks (read_file / grep_file), reasoning through each chunk before reading the next, following the paper-access protocol in your instructions."""


# ── Core pipeline ────────────────────────────────────────────────────
async def run_pipeline(paper_path: str, no_cal: bool = False) -> dict:
    paper_path_abs = os.path.abspath(paper_path)

    # Phase-1 reviewers (both OpenAI and Claude SDK paths) read the paper from
    # disk in chunks rather than receiving it inline. Grant read access to the
    # paper's dir up front so read_file/grep_file permit it.
    allow_path(str(Path(paper_path_abs).parent))

    review_prompt = REVIEW_PROMPT.format(paper_path=paper_path_abs)

    print("  Phase 1: Running harsh critic ...")
    if HARSH_SDK_MODEL is not None:
        from claude_merger import run_harsh_claude_sdk
        harsh_text, harsh_sdk_usage = await run_harsh_claude_sdk(
            HARSH_SDK_MODEL, review_prompt, str(Path(paper_path_abs).parent), harsh_sdk_system_prompt
        )
        harsh_openai_usage = None
    else:
        harsh_text, harsh_openai_usage = await run_agent_with_retry(harsh, review_prompt)
        harsh_sdk_usage = None

    agent_usages: dict = {"Harsh Critic": harsh_openai_usage}
    sdk_usages: dict = {}
    if harsh_sdk_usage is not None:
        sdk_usages["Harsh Critic"] = harsh_sdk_usage
    labeled = [f"### Harsh Critic\n{harsh_text}"]

    print("  Phase 2: Merger ...")
    start_time = time.monotonic()
    if MERGER_SDK_MODEL is not None:
        from claude_merger import run_merger_claude_sdk
        merger_prompt = (
            f"Here is the paper being reviewed (extracted from PDF — formatting "
            f"artifacts are parser issues, not paper problems):\n\n"
            f"Paper path: {paper_path_abs}, read it in chunks.\n\n"
            f"Human reviews directory (for calibration): {HUMAN_REVIEW_DIR}\n\n"
            f"Here is the input review:\n\n{chr(10).join(labeled)}\n\n"
            f"Now produce the final consolidated review following your instructions. "
            f"Cross-check every weakness against the actual paper before including it."
        )
        merged_review, merger_sdk_usage = await run_merger_claude_sdk(
            MERGER_SDK_MODEL, merger_prompt, str(Path(paper_path_abs).parent), no_cal=no_cal
        )
        sdk_usages["Merger"] = merger_sdk_usage
        agent_usages["Merger"] = None  # SDK usage tracked separately below
    else:
        merger_prompt = (
            f"Here is the paper being reviewed (extracted from PDF — formatting "
            f"artifacts are parser issues, not paper problems).\n\n"
            f"Paper path: {paper_path_abs} — use read_file (which reads the whole file by default; do not pass start_line/end_line unless you specifically need a slice) or grep_file to read it.\n\n"
            f"Human reviews directory (for calibration): {HUMAN_REVIEW_DIR}\n\n"
            f"Here is the input review:\n\n{chr(10).join(labeled)}\n\n"
            f"Now produce the final consolidated review following your instructions. "
            f"Cross-check every weakness against the actual paper before including it."
        )
        merged_review, merger_usage = await run_agent_with_retry(merger, merger_prompt)
        merger_usage.duration_ms = int((time.monotonic() - start_time) * 1000)
        agent_usages["Merger"] = merger_usage

    scorer_output = float(merged_review.split("<score>")[1].split("</score>")[0]) if "<score>" in merged_review else -1
    decision = (merged_review.split("<decision>")[1].split("</decision>")[0]) if "<decision>" in merged_review else "N/A"

    if scorer_output == -1 or decision == "N/A":
        print(f"  Parsing failed (score={scorer_output}, decision={decision}); re-extracting with {EXTRACTOR_MODEL}")
        extractor_resp = await api_client.chat.completions.create(
            model=EXTRACTOR_MODEL,
            messages=[
                {"role": "system", "content": "Extract the final numeric score and accept/reject decision from a paper review. Respond with exactly: <score>NUMBER</score><decision>Accept|Reject</decision>. No other text. If you cannot see a score, return -100! If you cannot see a decision, return N/A! You should NOT guess the score."},
                {"role": "user", "content": merged_review},
            ],
            extra_body={"reasoning": {"enabled": False}},
        )
        extracted = extractor_resp.choices[0].message.content
        if scorer_output == -1 and "<score>" in extracted:
            scorer_output = float(extracted.split("<score>")[1].split("</score>")[0])
        if decision == "N/A" and "<decision>" in extracted:
            decision = extracted.split("<decision>")[1].split("</decision>")[0]
        print(f"  [extractor] score={scorer_output} decision={decision}")

    total_input = total_output = total_tokens = 0
    token_lines = []
    for agent_name, usage in agent_usages.items():
        if usage is None:
            token_lines.append(f"  {agent_name}: N/A (claude_sdk path)")
        else:
            cached = usage.input_tokens_details.cached_tokens
            reasoning = usage.output_tokens_details.reasoning_tokens
            token_lines.append(
                f"  {agent_name}: input={usage.input_tokens} (cached={cached}) "
                f"output={usage.output_tokens} (reasoning={reasoning}) "
                f"total={usage.total_tokens} requests={usage.requests}"
            )
            total_input += usage.input_tokens
            total_output += usage.output_tokens
            total_tokens += usage.total_tokens
    token_lines.append(f"  TOTAL: input={total_input} output={total_output} total={total_tokens}")

    sdk_lines = []
    sdk_total_cost = 0.0
    for sdk_name, su in sdk_usages.items():
        u = su["usage"]
        sdk_lines.append(f"  [{sdk_name}]")
        sdk_lines.append(f"    Model: {su['model']}")
        sdk_lines.append(f"    Session ID: {su['session_id']}")
        sdk_lines.append(f"    Cost (USD): {su['total_cost_usd']}")
        sdk_lines.append(f"    Turns: {su['num_turns']}")
        sdk_lines.append(f"    Duration: total={su['duration_ms']}ms api={su['duration_api_ms']}ms")
        sdk_lines.append(
            f"    Tokens: input={u['input_tokens']} output={u['output_tokens']} "
            f"cache_read={u['cache_read_input_tokens']} cache_creation={u['cache_creation_input_tokens']}"
        )
        rl = su["rate_limit"]
        if rl:
            util = rl["utilization"]
            util_str = f"{util*100:.1f}%" if util is not None else "n/a"
            sdk_lines.append(
                f"    Plan usage: type={rl['type']} util={util_str} "
                f"status={rl['status']} overage={rl['overage_status']}"
            )
        sdk_total_cost += su["total_cost_usd"]
    if sdk_lines:
        sdk_lines.append(f"  TOTAL Claude SDK cost (USD): {sdk_total_cost:.4f}")

    log_path = RESULTS_DIR / "pipeline.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as log_f:
        log_f.write(f"\n{'='*60}\n")
        log_f.write(f"Paper: {paper_path}\n")
        log_f.write(f"Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
        log_f.write("\n--- Token Usage ---\n" + "\n".join(token_lines) + "\n")
        if sdk_lines:
            log_f.write("\n--- Claude SDK Usage ---\n" + "\n".join(sdk_lines) + "\n")
        log_f.write(f"\n--- Merged Inputs ---\n\n{chr(10).join(labeled)}\n")
        log_f.write(f"\n--- Merged Review ---\n{merged_review}\n")
        log_f.write(f"\n--- Scorer Output ---\n{scorer_output}\n")
        log_f.write(f"\n--- Decision ---\n{decision}\n")

    return {"merged_review": merged_review, "scorer_output": scorer_output, "decision": decision, "sdk_usages": sdk_usages}


# ── Score calibration against the shipped reference runs ─────────────
# results/claude.csv    — this pipeline on Claude Sonnet 4.6 (Claude Agent SDK)
# results/deepseek.csv  — this pipeline on DeepSeek V4 Flash (OpenAI Agents SDK)
# Both are 390-394 ICLR 2026 submissions with real reviewer scores + decisions.
# The calibration set is picked from the merger backend actually being run.
CALIBRATION_CSV = RESULTS_DIR / ("claude.csv" if MERGER_MODEL.startswith("claude_sdk:") else "deepseek.csv")


def calibrate(score: float, window: float = 0.5) -> dict:
    """Map a raw pipeline score onto the reference run: percentile, OLS-calibrated
    score against real reviewer averages, and empirical acceptance rate."""
    import numpy as np

    preds = []
    gts = []
    accepts = []
    with open(CALIBRATION_CSV, "r") as f:
        for row in csv.DictReader(f):
            preds.append(float(row["pred_score"]))
            gts.append(float(row["gt_avg_score"]))
            accepts.append(row["gt_binary"] == "Accept")
    preds = np.array(preds)
    gts = np.array(gts)
    accepts = np.array(accepts)

    below = (preds < score).sum()
    equal = np.isclose(preds, score).sum()
    percentile = (below + 0.5 * equal) / len(preds) * 100

    slope, intercept = np.polyfit(preds, gts, 1)
    fitted = slope * preds + intercept
    r = np.corrcoef(preds, gts)[0, 1]

    exact_mask = np.isclose(preds, score)
    window_mask = np.abs(preds - score) <= window

    return {
        "csv": str(CALIBRATION_CSV),
        "n": len(preds),
        "percentile": percentile,
        "calibrated_score": slope * score + intercept,
        "slope": slope,
        "intercept": intercept,
        "pearson_r": r,
        "r2": r ** 2,
        "residual_mae": float(np.abs(gts - fitted).mean()),
        "exact_rate": accepts[exact_mask].mean() if exact_mask.any() else float("nan"),
        "exact_n": int(exact_mask.sum()),
        "window": window,
        "window_rate": accepts[window_mask].mean() if window_mask.any() else float("nan"),
        "window_n": int(window_mask.sum()),
    }


# ── PDF -> markdown ──────────────────────────────────────────────────
from datalab_sdk import AsyncDatalabClient, ConvertOptions


async def pdf_to_markdown(pdf_path: Path) -> str:
    options = ConvertOptions(
        output_format="markdown",
        mode="fast",
        paginate=True,
        page_range="0-9",
        token_efficient_markdown=True,
    )
    async with AsyncDatalabClient() as client:
        result = await client.convert(pdf_path, options=options)
    return result.markdown + "\n\n Rest of paper (reference and Appendix) is removed."


# ── Single paper ─────────────────────────────────────────────────────
async def run_single_paper(paper_path: str, no_cal: bool = False, skip_calibration: bool = False):
    print(f"Reviewing: {paper_path}")

    if paper_path.endswith(".pdf"):
        md = await pdf_to_markdown(Path(paper_path))
        md = re.sub(r"Published as a conference paper at ICLR \d{4}\s*\n?", "", md)
        md_path = Path(paper_path).with_suffix(".md")
        md_path.write_text(md, encoding="utf-8")
        paper_path = str(md_path)
        print(f"Converted PDF to markdown: {paper_path}")

    result = await run_pipeline(paper_path, no_cal=no_cal)
    print(f"\n{'=' * 72}\nFINAL REVIEW\n{'=' * 72}\n{result['merged_review']}")
    score = result["scorer_output"]
    cal = None
    if score != -1:
        print(f"\nPredicted score: {score}")
        if not skip_calibration:
            cal = calibrate(score)
            print(f"\n{'=' * 72}\nCalibration ({Path(cal['csv']).name}, n={cal['n']})\n{'=' * 72}")
            print(f"  Percentile of score={score}: {cal['percentile']:.1f}%")
            print(f"  Calibrated score (OLS vs real reviewer avg): {cal['calibrated_score']:.2f}")
            print(f"    fit: gt = {cal['slope']:.3f} * pred + {cal['intercept']:.3f}  "
                  f"(pearson r={cal['pearson_r']:.3f}, R2={cal['r2']:.3f}, residual MAE={cal['residual_mae']:.2f})")
            print(f"  Acceptance rate @ score={score}: {cal['exact_rate']:.2%} (n={cal['exact_n']})")
            print(f"  Acceptance rate @ score={score}+/-{cal['window']}: {cal['window_rate']:.2%} (n={cal['window_n']})")

    sdk_usages = result["sdk_usages"]
    if sdk_usages:
        print(f"\n{'=' * 72}\nClaude SDK Usage\n{'=' * 72}")
        total_cost = 0.0
        for name, su in sdk_usages.items():
            u = su["usage"]
            print(f"  [{name}]")
            print(f"    Model:         {su['model']}")
            print(f"    Session ID:    {su['session_id']}")
            print(f"    Cost (USD):    ${su['total_cost_usd']}")
            print(f"    Turns:         {su['num_turns']}")
            print(f"    Duration:      total={su['duration_ms']}ms api={su['duration_api_ms']}ms")
            print(f"    Input tokens:  {u['input_tokens']}")
            print(f"    Output tokens: {u['output_tokens']}")
            print(f"    Cache read:    {u['cache_read_input_tokens']}")
            print(f"    Cache create:  {u['cache_creation_input_tokens']}")
            rl = su["rate_limit"]
            if rl:
                util = rl["utilization"]
                util_str = f"{util*100:.1f}%" if util is not None else "n/a"
                print(f"    Plan usage:    type={rl['type']} util={util_str} status={rl['status']} overage={rl['overage_status']}")
            total_cost += su["total_cost_usd"]
        print(f"  TOTAL Claude SDK cost (USD): ${total_cost:.4f}")

    out_dir = RESULTS_DIR / "reviews"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / (os.path.basename(paper_path).split(".")[0] + f"_review_{time.strftime('%Y_%m_%d_%H_%M_%S')}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Review of {paper_path}\n\n")
        f.write(result["merged_review"])
        if score != -1:
            f.write(f"\n\n**Predicted score: {score}**\n")
        if cal is not None:
            f.write(f"\n**Percentile of score={score}: {cal['percentile']:.1f}% (n={cal['n']}, {Path(cal['csv']).name})**\n")
            f.write(f"\n**Calibrated score (OLS vs real reviewer avg): {cal['calibrated_score']:.2f}**\n")
            f.write(f"\n**Acceptance rate @ score={score}: {cal['exact_rate']:.2%} (n={cal['exact_n']})**\n")
            f.write(f"\n**Acceptance rate @ score={score}+/-{cal['window']}: {cal['window_rate']:.2%} (n={cal['window_n']})**\n")
    print(f"\nReview written to {out_path}")


# ── CLI ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ARD-Review: agentic paper reviewer")
    parser.add_argument("--single_paper", type=str, required=True, help="Path to the paper (.pdf, .md or .txt)")
    parser.add_argument("--no_cal", action="store_true", help="Skip calibration-anchor retrieval; score on paper merits alone")
    parser.add_argument("--skip_calibration", action="store_true", help="Do not map the raw score onto the reference run in results/")
    args = parser.parse_args()

    asyncio.run(run_single_paper(args.single_paper, no_cal=args.no_cal, skip_calibration=args.skip_calibration))

"""
Claude Agent SDK path for main.py.
Used when HARSH_MODEL / MERGER_MODEL start with 'claude_sdk:'.

The file-access and calibration-RAG tools are re-exposed to the Claude Agent SDK
as an in-process MCP server; the underlying corpus/index lives in tools.py.
"""
from __future__ import annotations

import os

from paths import prompt_path
from tools import CALIBRATION_REVIEW_DIR, search_file_impl


def make_merger_mcp_server(paper_dir: str, no_cal: bool = False):
    from claude_agent_sdk import create_sdk_mcp_server, tool

    allowed_paths = [os.path.abspath(paper_dir), os.path.abspath(CALIBRATION_REVIEW_DIR)]

    def check_path(path: str) -> str | None:
        resolved = os.path.abspath(path)
        if any(resolved.startswith(ap) for ap in allowed_paths):
            return None
        return f"ERROR: Access denied. Path '{resolved}' is not under any allowed directory: {allowed_paths}. The agent may access only the specific allowed paths. Do not explore directories or nearby paths; only double-check whether the requested path was misspelled."

    @tool(
        "read_file",
        "Read lines from a file. Returns lines numbered start_line to end_line (1-based). If end_line is 0, reads to EOF. If access is denied, only re-check whether the requested path is misspelled; do not explore directories or try nearby paths.",
        {"abs_path": str, "start_line": int, "end_line": int},
    )
    async def read_file(args: dict) -> dict:
        abs_path = args["abs_path"]
        start_line = args["start_line"] if "start_line" in args else 1
        end_line = args["end_line"] if "end_line" in args else 0
        print(f"  [claude:read_file] {abs_path} lines {start_line}-{end_line or 'EOF'}")
        err = check_path(abs_path)
        if err:
            return {"content": [{"type": "text", "text": err}], "is_error": True}
        with open(abs_path, "r", errors="replace") as fh:
            lines = fh.readlines()
        selected = lines[max(0, start_line - 1):end_line if end_line > 0 else len(lines)]
        text = "".join(f"{start_line + i}: {line}" for i, line in enumerate(selected))
        return {"content": [{"type": "text", "text": text}]}

    @tool(
        "grep_file",
        "Search a single file for a substring pattern. Returns matching lines with line numbers. If access is denied, only re-check whether the requested path is misspelled; do not explore directories or try nearby paths.",
        {"pattern": str, "abs_path": str},
    )
    async def grep_file(args: dict) -> dict:
        import re
        pattern = args["pattern"]
        abs_path = args["abs_path"]
        print(f"  [merger:grep_file] pattern='{pattern}' in '{abs_path}'")
        err = check_path(abs_path)
        if err:
            return {"content": [{"type": "text", "text": err}], "is_error": True}
        if not os.path.isfile(abs_path):
            return {"content": [{"type": "text", "text": f"ERROR: '{abs_path}' is not a file. Do not explore directories or nearby paths; only double-check whether the requested path was misspelled."}], "is_error": True}
        matches = []
        with open(abs_path, "r", errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                if re.search(pattern, line):
                    matches.append(f"{i}: {line.rstrip()}")
        text = "\n".join(matches) if matches else "No matches found."
        return {"content": [{"type": "text", "text": text}]}

    @tool(
        "draft_review",
        "Record the merger's post-filtering draft before calibration or final writing.",
        {"draft": str},
    )
    async def draft_review(args: dict) -> dict:
        return {"content": [{"type": "text", "text": "draft recorded"}]}

    @tool(
        "calibration_search",
        "RAG retrieval over the human-review corpus. Pass a batch of queries; each runs vector search and returns top-n hits with avg human score and first 1000 chars. Up to 3 calls total across the session (bracket -> narrow -> optional re-narrow); see the calibration protocol in the system prompt for when to use each round. Args: queries (list of {query: str, n?: int, low_score?: float, high_score?: float}).",
        {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "n": {"type": "integer"},
                            "low_score": {"type": "number"},
                            "high_score": {"type": "number"},
                        },
                        "required": ["query"],
                    },
                }
            },
            "required": ["queries"],
        },
    )
    async def calibration_search(args: dict) -> dict:
        queries = args["queries"]
        if not isinstance(queries, list) or not queries:
            return {"content": [{"type": "text", "text": "ERROR: 'queries' must be a non-empty list of query objects."}], "is_error": True}
        sections = []
        for i, q in enumerate(queries, 1):
            qtext = str(q["query"])
            n = int(q["n"]) if "n" in q else 4
            low_score = float(q["low_score"]) if "low_score" in q else -1.0
            high_score = float(q["high_score"]) if "high_score" in q else 11.0
            print(f"  [merger:calibration_search] q{i}='{qtext}' n={n} score=({low_score}, {high_score})")
            body = search_file_impl(qtext, n, "vector", low_score, high_score)
            sections.append(f"### Query {i}: {qtext!r}  (n={n}, score=({low_score}, {high_score}))\n{body}")
        return {"content": [{"type": "text", "text": "\n\n".join(sections)}]}

    tools = [read_file, grep_file, draft_review]
    if not no_cal:
        tools.append(calibration_search)
    return create_sdk_mcp_server(
        name="merger_fs",
        version="1.0.0",
        tools=tools,
    )


with open(prompt_path("cal_with.md"), "r") as _f:
    CAL_INSTRUCTION_WITH = _f.read()

with open(prompt_path("cal_without.md"), "r") as _f:
    CAL_INSTRUCTION_WITHOUT = _f.read()


async def run_claude_sdk_query(
    *,
    label: str,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    allowed_tools: list[str],
    mcp_servers: dict,
    max_turns: int,
) -> tuple[str, dict]:
    """
    Generic single-turn-style Claude SDK runner. Captures cost/usage from
    ResultMessage and returns (text, usage dict).
    """
    from claude_agent_sdk import (
        ClaudeSDKClient,
        ClaudeAgentOptions,
        AssistantMessage,
        TextBlock,
        ResultMessage,
        RateLimitEvent,
    )

    print(f"  [{label}] starting Claude Agent SDK ({model_id}) ...")

    options = ClaudeAgentOptions(
        model=model_id,
        allowed_tools=allowed_tools,
        permission_mode="bypassPermissions",
        disallowed_tools=["Read", "Glob", "Grep", "Bash", "Edit", "Write", "WebSearch", "WebFetch"],
        mcp_servers=mcp_servers,
        max_turns=max_turns,
        cwd="/tmp",
    )

    full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"

    result_text = ""
    sdk_usage: dict = {
        "model": model_id,
        "session_id": None,
        "total_cost_usd": None,
        "num_turns": None,
        "duration_ms": None,
        "duration_api_ms": None,
        "usage": None,
        "rate_limit": None,
    }
    async with ClaudeSDKClient(options=options) as sdk_client:
        await sdk_client.query(full_prompt)
        async for message in sdk_client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result_text += block.text
            elif isinstance(message, ResultMessage):
                sdk_usage["session_id"] = message.session_id
                sdk_usage["total_cost_usd"] = message.total_cost_usd
                sdk_usage["num_turns"] = message.num_turns
                sdk_usage["duration_ms"] = message.duration_ms
                sdk_usage["duration_api_ms"] = message.duration_api_ms
                sdk_usage["usage"] = message.usage
            elif isinstance(message, RateLimitEvent):
                info = message.rate_limit_info
                sdk_usage["rate_limit"] = {
                    "status": info.status,
                    "type": info.rate_limit_type,
                    "utilization": info.utilization,
                    "resets_at": info.resets_at,
                    "overage_status": info.overage_status,
                    "overage_resets_at": info.overage_resets_at,
                }

    if not result_text.strip():
        raise RuntimeError(f"[{label}] Claude Agent SDK returned empty output")

    print(f"  [{label}] done — {model_id} (Claude Agent SDK)")
    return result_text, sdk_usage


async def run_harsh_claude_sdk(model_id: str, harsh_prompt_user: str, paper_dir: str, system_prompt: str) -> tuple[str, dict]:
    """
    Run the Harsh Critic via Claude Agent SDK with only read_file (so it can
    read the paper from disk instead of receiving it inline).
    """
    mcp_server = make_merger_mcp_server(paper_dir, no_cal=True)
    return await run_claude_sdk_query(
        label="Harsh Critic",
        model_id=model_id,
        system_prompt=system_prompt,
        user_prompt=harsh_prompt_user,
        allowed_tools=["mcp__merger_fs__read_file"],
        mcp_servers={"merger_fs": mcp_server},
        max_turns=15,
    )


async def run_merger_claude_sdk(model_id: str, merger_prompt: str, paper_dir: str, no_cal: bool = False) -> tuple[str, dict]:
    """
    Run the merger agent via Claude Agent SDK.
    Returns (final merged review text, usage dict with cost/tokens/turns).
    """
    with open(prompt_path("merger.md"), "r") as f:
        system_prompt = f.read()
    system_prompt = system_prompt.replace(
        "{{PAPER_ACCESS_INSTRUCTION}}",
        "The paper path is provided in the user message. Use read_file to read the paper and verify reviewer claims directly.",
    )
    cal_instruction = CAL_INSTRUCTION_WITHOUT if no_cal else CAL_INSTRUCTION_WITH
    system_prompt = system_prompt.replace("{{CALIBRATION_INSTRUCTION}}", cal_instruction)

    mcp_server = make_merger_mcp_server(paper_dir, no_cal=no_cal)

    # Iterative RAG: merger brackets the score range with a first batch of
    # queries, then narrows with a second (and optionally third) batch inside
    # that range. Up to 3 calibration_search calls total. Anchors read via
    # read_file. No subagent.
    allowed_tools = [
        "mcp__merger_fs__read_file",
        "mcp__merger_fs__grep_file",
        "mcp__merger_fs__draft_review",
    ]
    if not no_cal:
        allowed_tools.append("mcp__merger_fs__calibration_search")

    return await run_claude_sdk_query(
        label="Merger",
        model_id=model_id,
        system_prompt=system_prompt,
        user_prompt=merger_prompt,
        allowed_tools=allowed_tools,
        mcp_servers={"merger_fs": mcp_server},
        max_turns=30,
    )

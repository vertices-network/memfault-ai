---
name: memfault-issue-analyzer
description: Analyze Memfault issues with AI-assisted firmware debugging workflows. Use when Codex needs to inspect Memfault issue metadata, traces, stack frames, firmware source context, generated root-cause reports, batch issue analysis, version filtering, or carefully supervised autonomous fix generation using this repository's Python tools.
---

# Memfault Issue Analyzer

Use this skill to help investigate Memfault firmware issues and produce actionable engineering analysis. The repository contains a Python CLI plus supporting modules for:

- Fetching Memfault issues and traces.
- Formatting crash metadata, thread state, registers, logs, and stack frames.
- Loading local firmware documentation and relevant source files.
- Asking Claude for root-cause analysis and validation guidance.
- Optionally tracking analyses and fix attempts in SQLite agent memory.

This skill directory lives at `memfault-issue-analyzer/`. In this source repository, the Python tool lives in the parent directory. Run repository commands from the parent directory unless the user has installed or copied the tool elsewhere.

## Required Setup

Confirm configuration before running tools:

- `MEMFAULT_API_KEY`
- `MEMFAULT_ORG_SLUG`
- `MEMFAULT_PROJECT_SLUG`
- `AI_CLIENT` (currently `anthropic`)
- `AI_MODEL`
- `ANTHROPIC_API_KEY`
- `SOURCE_CODE_PATH` only when source-context or fix workflows are needed

Never print secret values. It is fine to report whether a variable is set or missing.

From the parent repository root, install runtime dependencies only when needed:

```bash
pip install -r requirements.txt
```

## Core Workflow

1. Inspect the user request and decide whether it needs live Memfault/API access or local source analysis.
2. If only explaining or reviewing the repository, read the relevant Python modules directly.
3. If analyzing live issues, run the CLI from the parent repository with `python main.py` and use the interactive commands:
   - `list` to fetch issues.
   - `filter <status>` and `filter-version <version> <mode>` to narrow scope.
   - `sort devices desc` or `sort traces desc` to prioritize impact.
   - `analyze <issue-id>` or `analyze #<row>` to generate a report.
   - `batch-analyze` only after confirming API cost/time expectations.
4. Save generated analysis when the user needs an artifact. Reports are written under `analysis_results/`, which should stay ignored by git because it may contain private issue data.
5. Summarize findings with issue IDs, affected devices/traces, suspected root cause, recommended fix, validation plan, and any uncertainty.

## Source Context

When `SOURCE_CODE_PATH` is configured, the analyzer may read:

- `AGENT.md`, `CLAUDE.md`, `AI_CONTEXT.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`, or `README.md` from the firmware source tree.
- Up to several source files inferred from Memfault stack traces, titles, and messages.

Treat this data as potentially proprietary. Do not include large source excerpts in final answers unless the user explicitly asks and disclosure is appropriate.

Use `../docs/AGENT.md.example` as a template when the firmware repo lacks an `AGENT.md`.

## Autonomous Fix Safety

The `fix` and `auto-fix` commands generate reviewable fix drafts by default. They mutate the repository at `SOURCE_CODE_PATH` only when environment safety gates are explicitly enabled.

Default to analysis-only and draft-only behavior. Use mutating fix mode only when the user explicitly asks for it and understands the risk.

Before any autonomous fix run:

1. Confirm the target `SOURCE_CODE_PATH`.
2. Check the target git worktree status.
3. Preserve user changes; do not overwrite unrelated local work.
4. Prefer generating reviewable patches or analysis files over applying changes directly.
5. Enable mutation only with the explicit flags in `.env.example`.

After an autonomous fix attempt, inspect the resulting diff before reporting success.

## References

Load these files only when relevant:

- `../README.md` for user-facing setup and command overview.
- `references/VERSION_FILTERING.md` for firmware version filtering modes and examples.
- `references/TRACE_ENHANCEMENT.md` for trace/thread/stack context behavior.
- `references/AUTONOMOUS_MODE.md` for the agent memory and autonomous-fix workflow.
- `references/IMPLEMENTATION_SUMMARY.md` for historical design context, not as current behavior authority.

## Validation

For repository changes, run from the parent repository root:

```bash
python3 -m py_compile config.py memfault_client.py agent_memory.py ui.py claude_analyzer.py autonomous_agent.py main.py
```

If macOS Python tries to write bytecode outside the workspace, rerun with an approved environment or set an in-workspace cache location.

For skill metadata changes, run from the parent repository root:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" memfault-issue-analyzer
```

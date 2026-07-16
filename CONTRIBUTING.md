# Contributing

Thanks for helping improve the Memfault Issue Analyzer.

## Development Setup

```bash
python3 -m venv venv
. venv/bin/activate
pip install -e .
```

Copy `.env.example` to `.env` for local API-backed testing. Never commit `.env`, generated analysis output, or firmware/customer data.

## Validation

Before opening a pull request, run:

```bash
python3 -m py_compile config.py memfault_client.py agent_memory.py ui.py claude_analyzer.py autonomous_agent.py main.py
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" memfault-issue-analyzer
```

If the skill validator is not installed, run the Python compile check and mention that the skill validation was skipped.

## Pull Requests

- Keep changes narrowly scoped.
- Include documentation updates for behavior changes.
- Avoid committing generated `analysis_results/` files.
- Do not include private Memfault issue data, source snippets, device identifiers, or credentials.
- Treat autonomous fix behavior as security-sensitive; default behavior should remain non-mutating.

# Security Policy

## Reporting Vulnerabilities

Please do not open public issues for suspected vulnerabilities.

Email the maintainers or project owner with:

- Affected version or commit
- Reproduction steps
- Impact assessment
- Any relevant logs, with secrets redacted

## Data Handling

This tool can send Memfault issue metadata, traces, logs, stack frames, local documentation, and selected source snippets to Anthropic for analysis. Treat generated analysis files and `analysis_results/agent_memory.db` as potentially sensitive.

Before sharing artifacts publicly:

- Remove API keys and credentials
- Review issue data for device identifiers or customer data
- Review source snippets and stack traces for proprietary information
- Delete local `analysis_results/` content unless it is intentionally sanitized

## Autonomous Fix Safety

Fix commands generate drafts by default. Source mutation, git command execution, builds, and commits require explicit environment flags. Do not enable mutating mode on an untrusted repository or a dirty worktree.

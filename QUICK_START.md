# Quick Start: Autonomous Agent

## 30-Second Setup

```bash
# 1. Set your AI model and source code path in .env
echo "AI_CLIENT=anthropic" >> .env
echo "AI_MODEL=claude-opus-4-6" >> .env
echo "SOURCE_CODE_PATH=/path/to/firmware" >> .env

# 2. Run the analyzer
python main.py
```

## First Run: Batch Analysis

```
memfault> batch-analyze
```

This analyzes all your Memfault issues (~5 minutes for 20 issues).

## Try Autonomous Mode

```
memfault> auto-fix 1
```

This will:
1. ✅ Select high-impact analyzed issues
2. ✅ Generate code-change drafts with Claude
3. ✅ Save review artifacts under `analysis_results/fix_drafts/`
4. ✅ Append draft links to `analysis_results/issue_XXX.md`
5. ⚠️  Leave source files unchanged by default

## Check Progress

```
memfault> status
memfault> memory
```

## File Structure After Running

```
memfault-ai/
├── analysis_results/
│   ├── agent_memory.db          # SQLite database
│   ├── fix_drafts/              # Reviewable generated fixes
│   ├── issue_18047991_*.md      # Analysis + draft links
│   ├── issue_18254832_*.md
│   └── ...
```

## What the Agent Does

### Batch Analysis
- Fetches all issues from Memfault
- For each issue:
  - Loads source code context (AGENT.md)
  - Finds relevant source files
  - Analyzes with Claude (firmware expert mode)
  - Saves detailed analysis
  - Stores in memory database

### Autonomous Fix
- Selects top issues by device count
- For each issue:
  - Generates code changes with Claude
  - Includes:
    - Files to modify
    - Complete code snippets
    - Rationale for changes
    - Before/after examples
  - Saves a fix draft for review
  - Does not run git commands, write files, build, or commit unless safety flags are enabled

## Review Generated Fixes

```bash
# View generated fix drafts
ls analysis_results/fix_drafts/
```

The issue analysis file also links to the generated draft.

## Apply Fix Manually

1. Read the generated fix
2. Review the code changes
3. Apply to your codebase
4. Test thoroughly
5. Commit and push

## Enable Mutating Mode

The default mode is safe for public use: generated fixes are drafts only.

Set these flags only when you want the tool to mutate `SOURCE_CODE_PATH`:

```bash
MEMFAULT_AI_RUN_GIT_COMMANDS=true
MEMFAULT_AI_APPLY_FIXES=true
MEMFAULT_AI_COMMIT_FIXES=true
```

The agent refuses to apply changes when the target git worktree is dirty.

## Track Success

```python
from agent_memory import AgentMemory, FixStatus
from pathlib import Path

memory = AgentMemory(Path("analysis_results/agent_memory.db"))

# Mark as fixed
memory.update_fix_status("1804799173", FixStatus.COMPLETED)

# View stats
stats = memory.get_statistics()
print(f"Fixed {stats['successful_fixes']} of {stats['total_issues']} issues")
```

## Best Practices

1. **Start small**: Try `auto-fix 1` first
2. **Review everything**: Agent is a tool, not a replacement
3. **Test on hardware**: Don't deploy without validation
4. **Update AGENT.md**: Keep codebase docs current
5. **Track patterns**: Use agent memory to find systemic issues

## Troubleshooting

**"No issues found"**
→ Check your .env has correct Memfault credentials

**"Autonomous agent not available"**
→ Set SOURCE_CODE_PATH in .env

**"Failed to pull latest main"**
→ Git strategy execution is disabled by default; set `MEMFAULT_AI_RUN_GIT_COMMANDS=true` and ensure the git working directory is clean

## Next: Hardware Access

See [IMPLEMENTATION_SUMMARY.md](memfault-issue-analyzer/references/IMPLEMENTATION_SUMMARY.md) for discussion on Phase 3: Hardware-in-Loop testing.

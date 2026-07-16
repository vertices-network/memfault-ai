# Autonomous Agent Mode

The Memfault AI Analyzer can analyze firmware issues and generate reviewable fix drafts.

## Overview

The autonomous agent workflow:

1. **Batch Analysis**: Analyzes all Memfault issues and stores results in persistent memory
2. **Agent Memory**: SQLite database tracks issues, analyses, fix attempts, and branches
3. **Autonomous Fix Drafts**: Agent can generate proposed code changes with Claude and save them for review
4. **Opt-in Mutation**: Running git commands, applying edits, building, and committing are disabled by default
5. **State Tracking**: Full history of what's been analyzed and attempted

## Quick Start

### 1. Configure Environment

```bash
# Required for autonomous mode
SOURCE_CODE_PATH=/path/to/your/firmware
AI_CLIENT=anthropic
AI_MODEL=claude-opus-4-6

# Optional safety gates. Defaults shown here are non-mutating.
MEMFAULT_AI_RUN_GIT_COMMANDS=false
MEMFAULT_AI_APPLY_FIXES=false
MEMFAULT_AI_BUILD_FIXES=true
MEMFAULT_AI_COMMIT_FIXES=false
```

### 2. Run Batch Analysis

```bash
python main.py
```

```
memfault> batch-analyze
```

This will:
- Fetch all issues from Memfault
- Analyze each one with Claude
- Store analyses in `analysis_results/`
- Save metadata to `analysis_results/agent_memory.db`

### 3. Run Autonomous Fix Mode

```
memfault> auto-fix 5
```

This will:
- Select top 5 issues by device count
- Generate a fix draft for each selected issue
- Save drafts under `analysis_results/fix_drafts/`
- Append draft links to each issue analysis file
- Leave source files unchanged unless safety gates are explicitly enabled

### 4. Check Progress

```
memfault> status
```

Shows breakdown by fix status:
- `analyzed` - Ready for fixing
- `fix_in_progress` - Currently being fixed
- `fix_created` - Fix generated, awaiting review
- `completed` - Successfully fixed

```
memfault> memory
```

Shows statistics:
- Total issues tracked
- Fix attempts made
- Success rate

## Agent Memory

The agent maintains persistent memory in SQLite:

### Issues Table
- Issue metadata (ID, title, message, counts)
- Analysis file path
- Fix status
- Branch name and commit SHA
- Attempt count
- Notes

### Fix Attempts Table
- Attempt number
- Timestamp
- Status (success/failure)
- Approach taken
- Changes made
- Test results
- Error messages

### Agent State Table
- Key-value storage for agent state
- Last processed issue
- Configuration snapshots

## Workflow Details

### Batch Analysis Workflow

```
Fetch Issues → For Each Issue:
  ├─ Check if already analyzed (skip if yes)
  ├─ Fetch detailed issue data
  ├─ Fetch sample traces
  ├─ Run Claude analysis (with source code context)
  ├─ Save to markdown file
  └─ Store in agent memory
```

### Autonomous Fix Workflow

```
For Each Issue to Fix:
  ├─ Discover workspace context
  ├─ Ask Claude for a proposed git/build strategy
  ├─ Generate a fix draft with Claude
  │   ├─ Include previous analysis
  │   ├─ Request specific code changes
  │   └─ Get file modifications
  ├─ Save reviewable draft to analysis_results/fix_drafts/
  ├─ Optionally apply edits if MEMFAULT_AI_APPLY_FIXES=true
  ├─ Optionally test changes with west build
  ├─ Optionally commit exact touched files
  └─ Update agent memory
```

## Safety Defaults

By default, the agent:

- ✅ Generates detailed fix instructions
- ✅ Saves reviewable fix drafts
- ✅ Records draft attempts in agent memory
- ✅ Refuses to mutate source files
- ✅ Refuses to apply changes to a dirty worktree when mutation is enabled

The fix draft includes:
- Specific files to modify
- Complete code snippets
- Rationale for each change
- Before/after examples

### Enabling Mutating Mode

Set these flags only when you explicitly want the tool to modify `SOURCE_CODE_PATH`:

```bash
MEMFAULT_AI_RUN_GIT_COMMANDS=true
MEMFAULT_AI_APPLY_FIXES=true
MEMFAULT_AI_COMMIT_FIXES=true
```

Mutation mode adds these guardrails:
- AI-proposed git strategy commands are restricted to `git`, `west`, and `cd`
- Shell control tokens such as `&&`, `;`, and pipes are rejected
- Edit paths must be relative and remain under `SOURCE_CODE_PATH`
- Generated edits must match exactly once before files are written
- Commits stage only files touched by the agent

### Why Review First?

For safety and quality:
1. **Firmware is critical** - bugs can brick devices
2. **Context matters** - AI needs human verification
3. **Testing is essential** - compilation is minimum, but not sufficient
4. **Hardware dependencies** - some fixes need hardware validation

## Future Enhancements

### Phase 2: Safer Automated Application
- Generate patch files instead of direct edits
- Add unit/static-analysis hooks
- Create PRs with fix details

### Phase 3: Hardware-in-Loop
- Request hardware access
- Run fixes on test bench
- Validate sensor readings
- Stress test with actual hardware

### Phase 4: Learning & Improvement
- Track fix success rates
- Learn from failed attempts
- Build pattern library
- Suggest preventive changes

## Advanced Usage

### Filter by Status

```python
from agent_memory import AgentMemory, FixStatus

memory = AgentMemory(Path("analysis_results/agent_memory.db"))

# Get all analyzed issues
analyzed = memory.get_issues_by_status(FixStatus.ANALYZED)

# Get failed attempts
failed = memory.get_issues_by_status(FixStatus.FAILED)
```

### Manual Fix Tracking

```python
# Mark issue as fixed externally
memory.update_fix_status(
    issue_id="1804799173",
    status=FixStatus.COMPLETED,
    notes="Fixed manually in PR #123"
)

# Record attempt
memory.record_fix_attempt(
    issue_id="1804799173",
    status="completed",
    approach="Manual fix based on Claude analysis",
    changes_made="Updated runner_process_jobs_thread() to handle payload ID 0"
)
```

### Query Statistics

```python
stats = memory.get_statistics()
print(f"Success rate: {stats['successful_fixes'] / stats['total_issues']:.1%}")
```

## Safety Guidelines

1. **Always review generated fixes** before applying
2. **Test on development hardware** first
3. **Use feature flags** for risky changes
4. **Monitor Memfault** after deploying fixes
5. **Keep agent memory backed up** (it's valuable data)

## Git Workflow

In default dry-run mode, the agent does not run git commands. If mutating mode is enabled, use a workflow like:

```bash
# 1. Start from clean main
git checkout main
git pull origin main

# 2. Create fix branch
git checkout -b fix/issue-12345678-error-at-runner

# 3. Apply fix (manual or automated)
# ... make changes ...

# 4. Commit
git add <files touched by this fix>
git commit -m "Fix issue 12345678: Error at runner_process_jobs_thread

This fix was automatically generated by the Memfault AI Agent.

Issue ID: 1804799173"

# 5. Push manually after review
git push -u origin fix/issue-12345678-error-at-runner

# 6. Create PR (future: automated)
```

## Troubleshooting

### "Agent memory not initialized"
- Check that `analysis_results/` directory exists
- Database is created automatically on first run

### "Autonomous agent not available"
- Set `SOURCE_CODE_PATH` in `.env`
- Ensure path points to valid git repository

### "No analyzed issues ready for fixing"
- Run `batch-analyze` first
- Check `status` to see issue states

### "Failed to pull latest main"
- Git strategy execution is disabled by default; set `MEMFAULT_AI_RUN_GIT_COMMANDS=true`
- Ensure clean git state (no uncommitted changes)
- Check network connectivity
- Verify git remote is configured

## Best Practices

1. **Run batch-analyze overnight** - analyzing 100 issues takes time
2. **Fix in small batches** - start with 1-2 issues to verify workflow
3. **Review all fixes** - agent is a tool, not a replacement for engineers
4. **Track patterns** - use agent memory to identify systemic issues
5. **Update AGENT.md** - keep codebase documentation current

## Integration with CI/CD

### Automated Analysis Pipeline

```yaml
# .github/workflows/memfault-analysis.yml
name: Memfault Analysis

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run batch analysis
        env:
          MEMFAULT_API_KEY: ${{ secrets.MEMFAULT_API_KEY }}
          MEMFAULT_ORG_SLUG: ${{ secrets.MEMFAULT_ORG_SLUG }}
          MEMFAULT_PROJECT_SLUG: ${{ secrets.MEMFAULT_PROJECT_SLUG }}
          AI_CLIENT: anthropic
          AI_MODEL: claude-opus-4-6
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          python main.py <<EOF
          batch-analyze
          status
          quit
          EOF
```

## Example Session

```
$ python main.py

✓ Agent memory initialized: analysis_results/agent_memory.db
✓ Source code path configured: /Users/dev/firmware
✓ Autonomous agent ready (dry-run: generate fix drafts only)

memfault> batch-analyze
Fetching all issues...
Found 20 issues

Analyze all 20 issues? This may take a while. [y/n]: y

Analyzing issues... ━━━━━━━━━━━━━━━━━━━━━━━━━━ 20/20

✓ Batch analysis complete!

Agent Memory Statistics

  Total Issues:      20
  Total Attempts:    0
  Successful Fixes:  0

By Status:
  analyzed            : 20

memfault> auto-fix 3
Autonomous Fix Mode
Safety mode: dry-run: generate fix drafts only
Will process up to 3 issues

Found 20 analyzed issues
Will process top 3 by impact:

  1. Error at runner_process_jobs_thread (1125 devices)
  2. HeartbeatFromJetson timeout at timeout_default.c (1010 devices)
  3. Error at polarizer_wheel_control (942 devices)

Proceed with fix draft generation? [y/n]: y

═══════════════════════════════════════════════════════════
Attempting to fix issue: 1804799173
Error at runner_process_jobs_thread
Safety mode: dry-run: generate fix drafts only
═══════════════════════════════════════════════════════════

Generating fix with Claude...
✓ Fix draft saved to analysis_results/fix_drafts/fix_1804799173_*.md
Fix draft generated for manual review.

[... continues for other issues ...]

Autonomous run complete!
Completed workflows: 3/3

memfault> status

Agent Status

  analyzed            :  17 issues
  fix_created         :   3 issues
```

## Hardware Access (Future)

Design for hardware-in-loop testing:

```python
class HardwareAccess:
    """Interface for requesting hardware access."""

    def request_device(self, requirements: Dict) -> Optional[Device]:
        """Request a test device matching requirements."""
        pass

    def run_test(self, device: Device, test_script: str) -> TestResults:
        """Execute test on device."""
        pass

    def release_device(self, device: Device):
        """Release device back to pool."""
        pass
```

This will be discussed and implemented in a future phase.

# Memfault Issue Analyzer

An interactive CLI tool and agent workflow that browses Memfault issues, provides AI-powered root cause analysis, and generates reviewable fix drafts for firmware issues.

## Features

### Interactive Mode
- Browse and filter Memfault issues by status
- Sort by device count, trace count, or date
- View detailed issue information including traces
- AI-powered root cause analysis using Claude
- Save analysis results to markdown files
- Interactive command-line interface with autocomplete

### Autonomous Mode
- **Batch Analysis**: Analyze all issues automatically and store in persistent memory
- **Agent Memory**: SQLite database tracks issues, analyses, fix attempts, and git branches
- **Fix Drafts by Default**: Generate reviewable code-change drafts without modifying source files
- **State Tracking**: Full history of what's been analyzed and attempted
- **Opt-in Git Integration**: Git commands, source edits, builds, and commits are disabled unless explicitly enabled
- **Progress Monitoring**: Track success rates and fix status

See [AUTONOMOUS_MODE.md](memfault-issue-analyzer/references/AUTONOMOUS_MODE.md) for detailed documentation.

Codex skill files and references are kept together in [memfault-issue-analyzer/](memfault-issue-analyzer/). That directory can be copied or installed as the skill folder.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables:
```bash
cp .env.example .env
```

Edit `.env` and add your credentials:
- `MEMFAULT_API_KEY`: Your Memfault API key (from Memfault dashboard > Settings > API Keys)
- `MEMFAULT_ORG_SLUG`: Your organization slug (visible in Memfault URLs)
- `MEMFAULT_PROJECT_SLUG`: Your project slug (visible in Memfault URLs)
- `AI_CLIENT`: AI client/provider name. Currently only `anthropic` is supported.
- `AI_MODEL`: Anthropic model to use (default: `claude-opus-4-6`)
- `ANTHROPIC_API_KEY`: Your Anthropic API key (from console.anthropic.com)
- `SOURCE_CODE_PATH` (optional): Path to your local source code directory for enhanced analysis
- `MEMFAULT_AI_RUN_GIT_COMMANDS=false` (optional): Execute validated AI-proposed git strategy commands
- `MEMFAULT_AI_APPLY_FIXES=false` (optional): Apply generated edits to `SOURCE_CODE_PATH`
- `MEMFAULT_AI_BUILD_FIXES=true` (optional): Run `west build` after applying edits
- `MEMFAULT_AI_COMMIT_FIXES=false` (optional): Commit applied edits

## Usage

Run the analyzer:
```bash
python main.py
```

### Available Commands

**Interactive Mode:**
- `list` - Show all issues
- `analyze <id or #row>` - Analyze a specific issue with AI
- `filter <status>` - Filter by status (unresolved/resolved/muted/merged/all)
- `sort <field> [order]` - Sort by devices, traces, or date

**Autonomous Mode:**
- `batch-analyze` - Analyze all issues and store in agent memory
- `fix <id or #row>` - Generate a fix draft for one issue
- `auto-fix [N]` - Generate fix drafts for the top N analyzed issues (default: 5)
- `status` - Show agent status and progress
- `memory` - Show agent memory statistics

**General:**
- `help` - Show help
- `quit` - Exit

### Example Session

**Interactive Mode:**
```
memfault> list
# Shows table of issues

memfault> sort devices
# Sort by device count (highest impact first)

memfault> analyze #1
# Fetches issue details and provides AI analysis
```

**Autonomous Mode:**
```
memfault> batch-analyze
# Analyzes all 20 issues with Claude...
✓ Batch analysis complete!

memfault> auto-fix 3
# Generates reviewable fix drafts for the top 3 issues by impact
# Does not modify source files unless explicit safety flags are enabled

memfault> status
# Shows what's been analyzed and drafted

memfault> memory
# Shows success rate and statistics
```

## How It Works

1. **Fetch Issues**: Connects to Memfault API to retrieve issue data
2. **Browse**: Interactive table view with filtering and sorting options
3. **Analyze**: Claude provides expert firmware engineering analysis:
   - Detailed root cause identification (not just symptoms)
   - Specific code-level fix recommendations with line numbers
   - Impact assessment (severity, scope, urgency)
   - Technical details (threading, memory, hardware interaction)
   - Comprehensive validation strategy
   - Regression prevention recommendations
4. **Source Code Context**: Automatically finds and includes relevant source files
5. **Codebase Documentation**: Reads AGENT.md or similar docs for project context
6. **Save**: Export detailed analysis to markdown files
7. **Draft Fixes**: Generate reviewable fix drafts under `analysis_results/fix_drafts/`

## Enhanced Analysis Features

### Automatic Context Loading

The analyzer automatically looks for and includes:
- **AGENT.md**: AI-specific codebase context (recommended)
- **ARCHITECTURE.md**: System architecture documentation
- **README.md**: Project overview
- **Relevant source files**: Automatically finds files related to the error

### Firmware-Specific Analysis

Claude analyzes issues with firmware engineering expertise:
- Race conditions and concurrency issues
- Memory corruption patterns
- Hardware interaction problems
- Timing and ISR context issues
- RTOS-specific concerns
- Power state transitions

### Creating AGENT.md

For best results, create an `AGENT.md` file in your source code root with:
- Project overview and architecture
- Component descriptions
- Threading model and critical sections
- Common issue patterns and fixes
- Memory layout and constraints
- Error handling philosophy

See `docs/AGENT.md.example` in this repo for a template.

## API References

- [Memfault API Documentation](https://api-docs.memfault.com/)
- [Memfault Docs](https://docs.memfault.com/)
- [Anthropic API Documentation](https://docs.anthropic.com/)

## Output

Analysis results are saved to `analysis_results/` directory with timestamped filenames.

## Privacy and Security

This tool can send Memfault issue metadata, traces, logs, stack frames, local documentation, and selected source snippets to Anthropic for analysis. Review your organization's data-sharing rules before using it on proprietary firmware or customer data.

Generated files under `analysis_results/` may contain sensitive issue details and are ignored by git. See [SECURITY.md](SECURITY.md) for reporting and handling guidance.

## Requirements

- Python 3.9+
- Memfault API access
- Anthropic API key

## License

MIT. See [LICENSE](LICENSE).

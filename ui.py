"""Interactive UI for the Memfault analyzer."""
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt, Confirm
from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from config import Config


console = Console()


class AnalyzerUI:
    """Interactive UI for browsing and analyzing issues."""

    def __init__(self):
        self.console = console
        self.current_page = 0
        self.items_per_page = 10

    def show_welcome(self):
        """Display welcome message."""
        welcome_text = """
# Memfault Issue Analyzer

An interactive tool to browse Memfault issues and get AI-powered root cause analysis.

**Commands:**

**Interactive Mode:**
- `list` - Show all issues
- `analyze <id or #row>` - Analyze issue by ID or row number (e.g., analyze #1)
- `filter <status>` - Filter by status (unresolved/resolved/muted/all)
- `filter-version <ver> [mode]` - Filter by firmware version
  - Modes: only, started, present, exclude, clear
- `versions` - Show all firmware versions and issue counts
- `sort <field> [order]` - Sort by devices, traces, or date (asc/desc)

**Autonomous Mode:**
- `batch-analyze` - Analyze all issues and store in agent memory
- `fix <id or #row>` - Generate a fix draft for a specific issue (e.g., fix #1)
- `auto-fix [N]` - Generate fix drafts for top N issues (default: 5)
- `status` - Show agent status and progress
- `memory` - Show agent memory statistics

**Navigation:**
- `help` - Show help
- `quit` - Exit
"""
        self.console.print(Panel(Markdown(welcome_text), border_style="blue"))

    def show_issues_table(self, issues: List[Dict], status_filter: Optional[str] = None, sort_info: Optional[str] = None):
        """Display issues in a formatted table."""
        if not issues:
            self.console.print("[yellow]No issues found.[/yellow]")
            return

        title_parts = ["Memfault Issues"]
        if status_filter:
            title_parts.append(f"Status: {status_filter}")
        if sort_info:
            title_parts.append(f"Sort: {sort_info}")

        table = Table(title=" | ".join(title_parts))

        table.add_column("#", style="cyan", no_wrap=True)
        table.add_column("ID", style="magenta", no_wrap=True)
        table.add_column("Title", style="white")
        table.add_column("Status", style="green")
        table.add_column("Devices", justify="right", style="red")
        table.add_column("Traces", justify="right", style="yellow")
        table.add_column("First Seen", style="blue")

        org = Config.MEMFAULT_ORG_SLUG
        project = Config.MEMFAULT_PROJECT_SLUG
        memfault_base_url = f"https://app.memfault.com/organizations/{org}/projects/{project}/issues"

        for idx, issue in enumerate(issues, 1):
            try:
                # Safely get issue ID - show full ID for copy/paste
                issue_id = issue.get("id", "N/A")
                if isinstance(issue_id, int):
                    issue_id = str(issue_id)

                # Safely get title
                title = issue.get("title", "N/A")
                if not isinstance(title, str):
                    title = str(title)

                # Safely get status
                status = issue.get("status", "N/A")
                if not isinstance(status, str):
                    status = str(status)

                table.add_row(
                    str(idx),
                    issue_id,
                    self._truncate(title, 45),
                    status,
                    str(issue.get("device_count", 0)),
                    str(issue.get("trace_count", 0)),
                    self._format_date(issue.get("first_seen"))
                )
            except Exception as e:
                self.console.print(f"[yellow]Warning: Error displaying issue {idx}: {e}[/yellow]")
                # Print the issue data for debugging
                self.console.print(f"[dim]Issue data: {issue}[/dim]")

        self.console.print(table)
        self.console.print(f"[dim]View issue on Memfault: {memfault_base_url}/<ID>[/dim]")

    def show_issue_details(self, issue: Dict, traces: List[Dict]):
        """Display detailed information about an issue."""
        self.console.print(f"\n[bold cyan]Issue Details: {issue.get('id', 'N/A')}[/bold cyan]\n")

        details = f"""
**Title**: {issue.get('title', 'N/A')}
**Status**: {issue.get('status', 'N/A')}
**First Seen**: {issue.get('first_seen', 'N/A')}
**Last Seen**: {issue.get('last_seen', 'N/A')}
**Total Traces**: {issue.get('trace_count', 'N/A')}
**Affected Devices**: {issue.get('device_count', 'N/A')}
"""

        if issue.get('reason'):
            details += f"\n**Reason**: {issue['reason']}"

        if issue.get('message'):
            details += f"\n**Message**: {issue['message']}"

        if issue.get('first_software_version'):
            details += f"\n**First Software Version**: {issue['first_software_version']}"

        if issue.get('last_software_version'):
            details += f"\n**Last Software Version**: {issue['last_software_version']}"

        if issue.get('software_version'):
            details += f"\n**Software Version**: {issue['software_version']}"

        if issue.get('hardware_version'):
            details += f"\n**Hardware Version**: {issue['hardware_version']}"

        if issue.get('is_missing_symbol_files'):
            details += f"\n**Missing Symbol Files**: Yes ⚠️"

        # Show additional fields that might be useful
        if issue.get('description'):
            details += f"\n**Description**: {issue['description']}"

        if issue.get('error_type'):
            details += f"\n**Error Type**: {issue['error_type']}"

        self.console.print(Panel(details, border_style="cyan"))

        # Show stack trace if available
        if issue.get('stack_trace'):
            self.console.print("\n[bold]Stack Trace:[/bold]")
            self.console.print(Panel(issue['stack_trace'], border_style="red"))

        if traces:
            self.console.print(f"\n[bold cyan]Trace Analysis ({len(traces)} traces with full details):[/bold cyan]\n")
            for idx, trace in enumerate(traces[:2], 1):  # Show up to 2 traces in detail
                device_serial = trace.get('device', {}).get('device_serial', 'N/A') if isinstance(trace.get('device'), dict) else 'N/A'
                self.console.print(f"[bold]Trace #{idx}:[/bold]")
                self.console.print(f"  Device: {device_serial}")
                self.console.print(f"  Captured: {trace.get('captured_date', 'N/A')}")
                self.console.print(f"  Reason: {trace.get('reason', 'N/A')}")
                self.console.print(f"  Title: {trace.get('title', 'N/A')}")

                # Show threads if available
                entries = trace.get('entries', {})
                if isinstance(entries, dict) and 'threads' in entries:
                    threads = entries['threads']
                    self.console.print(f"\n  [cyan]Threads ({len(threads)} found):[/cyan]")

                    for thread_idx, thread in enumerate(threads[:3], 1):  # Show up to 3 threads
                        name = thread.get('name', 'Unknown')
                        state = thread.get('state', 'unknown')
                        crashed = thread.get('crashed', False)
                        current = thread.get('current', False)

                        status_markers = []
                        if crashed:
                            status_markers.append("[red]CRASHED[/red]")
                        if current:
                            status_markers.append("[yellow]CURRENT[/yellow]")

                        status_str = " ".join(status_markers) if status_markers else ""
                        self.console.print(f"    Thread {thread.get('tid', thread_idx)}: {name} ({state}) {status_str}")

                        # Show stack trace for crashed or current thread
                        if (crashed or current) and 'stacktrace' in thread:
                            stacktrace = thread['stacktrace']
                            self.console.print(f"      [dim]Stack (showing top 10 frames):[/dim]")
                            for frame in stacktrace[:10]:
                                # Handle both trace formats
                                addr = frame.get('address', '')
                                func_name = frame.get('function', 'unknown')
                                file_name = frame.get('file', '')
                                line = frame.get('lineno', '')

                                # Handle nested function dict (coredump format)
                                if isinstance(func_name, dict):
                                    func_name = func_name.get('name', 'unknown')
                                    func_file = frame.get('function', {}).get('source_file', {})
                                    if isinstance(func_file, dict):
                                        file_name = func_file.get('path', '')
                                        line = frame.get('function', {}).get('source_line', '')

                                # Format output
                                if file_name and line:
                                    location = f"[cyan]{file_name}:{line}[/cyan]"
                                    self.console.print(f"        {func_name} at {location}")
                                elif file_name:
                                    self.console.print(f"        {func_name} in [cyan]{file_name}[/cyan]")
                                elif addr:
                                    self.console.print(f"        {addr}: {func_name}")
                                else:
                                    self.console.print(f"        {func_name}")

                # Show fault information if available
                if isinstance(entries, dict) and 'faults' in entries:
                    faults = entries['faults']
                    if 'notes' in faults and faults['notes']:
                        self.console.print(f"\n  [red]Fault Notes:[/red]")
                        for note in faults['notes']:
                            self.console.print(f"    • {note}")

                self.console.print()  # Blank line between traces
        else:
            self.console.print(f"\n[yellow]⚠ No detailed trace data available via API[/yellow]")
            self.console.print("[dim]Note: Some issue types (like simple asserts) may not have coredump data.[/dim]")
            self.console.print(f"[dim]Issue has {issue.get('trace_count', 0)} total traces, but detailed thread/stack info not accessible via REST API.[/dim]")

    def show_analysis(self, analysis: Dict):
        """Display Claude's analysis of an issue."""
        self.console.print("\n[bold green]═══ AI Analysis Results ═══[/bold green]\n")

        if "error" in analysis:
            self.console.print(f"[red]Error: {analysis['error']}[/red]")
            return

        md = Markdown(analysis.get("analysis", "No analysis available"))
        self.console.print(Panel(md, border_style="green", title="🔍 Detailed Root Cause Analysis", padding=(1, 2)))

    def save_analysis(self, issue_id: str, issue: Dict, analysis: Dict) -> Path:
        """Save analysis to a markdown file."""
        from config import Config

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"issue_{issue_id[:8]}_{timestamp}.md"
        filepath = Config.OUTPUT_DIR / filename

        content = f"""# Issue Analysis: {issue_id}

## Issue Information
- **Title**: {issue.get('title', 'N/A')}
- **Status**: {issue.get('status', 'N/A')}
- **First Seen**: {issue.get('first_seen', 'N/A')}
- **Last Seen**: {issue.get('last_seen', 'N/A')}
- **Trace Count**: {issue.get('trace_count', 'N/A')}
- **Device Count**: {issue.get('device_count', 'N/A')}

## AI Analysis

{analysis.get('analysis', 'No analysis available')}

---
*Analysis generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
*Model: {analysis.get('model_used', 'N/A')}*
"""

        filepath.write_text(content)
        return filepath

    def get_command(self, completer_words: Optional[List[str]] = None) -> str:
        """Get command from user with autocomplete."""
        if completer_words:
            completer = WordCompleter(completer_words, ignore_case=True)
            return prompt("memfault> ", completer=completer)
        return Prompt.ask("\n[bold cyan]memfault>[/bold cyan]")

    def confirm(self, message: str) -> bool:
        """Ask for user confirmation."""
        return Confirm.ask(message)

    @staticmethod
    def _truncate(text: str, length: int) -> str:
        """Truncate text to specified length."""
        return text[:length] + "..." if len(text) > length else text

    @staticmethod
    def _format_date(date_str: Optional[str]) -> str:
        """Format date string for display."""
        if not date_str:
            return "N/A"
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d")
        except:
            return date_str[:10] if len(date_str) >= 10 else date_str

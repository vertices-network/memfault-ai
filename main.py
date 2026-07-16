#!/usr/bin/env python3
"""Main entry point for the Memfault Issue Analyzer."""
import sys
from pathlib import Path
from typing import Optional
from anthropic import Anthropic
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from config import Config
from memfault_client import create_client
from claude_analyzer import create_analyzer
from agent_memory import AgentMemory, FixStatus
from autonomous_agent import AutonomousAgent
from ui import AnalyzerUI


class MemfaultAnalyzer:
    """Main application controller."""

    def __init__(self):
        self.ui = AnalyzerUI()
        self.memfault_client = None
        self.claude_analyzer = None
        self.current_issues = []
        self.all_issues = []  # Store all issues before filtering
        self.status_filter = None
        self.version_filter = None
        self.version_filter_mode = "only"
        self.sort_by = None
        self.sort_order = "desc"  # desc or asc
        self.memory = None
        self.agent = None

    def initialize(self):
        """Initialize API clients."""
        try:
            Config.validate()
            self.memfault_client = create_client()
            self.claude_analyzer = create_analyzer()
            self.ui.console.print(
                f"[green]✓ AI client: {Config.AI_CLIENT} / model: {Config.AI_MODEL}[/green]"
            )

            # Initialize agent memory
            memory_path = Config.OUTPUT_DIR / "agent_memory.db"
            self.memory = AgentMemory(memory_path)
            self.ui.console.print(f"[green]✓ Agent memory initialized: {memory_path}[/green]")

            # Initialize autonomous agent if source code path is configured
            if Config.SOURCE_CODE_PATH and Config.SOURCE_CODE_PATH.exists():
                self.ui.console.print(f"[green]✓ Source code path configured: {Config.SOURCE_CODE_PATH}[/green]")
                anthropic_client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)
                self.agent = AutonomousAgent(
                    self.memory,
                    Config.SOURCE_CODE_PATH,
                    anthropic_client,
                    model=Config.AI_MODEL,
                    ai_client=Config.AI_CLIENT,
                )
                self.ui.console.print(
                    f"[green]✓ Autonomous agent ready ({self.agent.describe_safety_mode()})[/green]"
                )
            else:
                self.ui.console.print("[yellow]ℹ Source code path not configured (autonomous mode disabled)[/yellow]")

            return True
        except ValueError as e:
            self.ui.console.print(f"[red]Configuration Error:[/red] {e}")
            return False
        except Exception as e:
            self.ui.console.print(f"[red]Initialization Error:[/red] {e}")
            return False

    def run(self):
        """Main application loop."""
        if not self.initialize():
            sys.exit(1)

        self.ui.show_welcome()
        self.list_issues()

        commands = [
            "list", "analyze", "filter", "filter-version", "sort", "versions",
            "batch-analyze", "auto-fix", "fix", "status", "memory",
            "next", "prev", "help", "quit", "exit"
        ]

        while True:
            try:
                command = self.ui.get_command(commands).strip().lower()

                if not command:
                    continue

                if command in ["quit", "exit"]:
                    self.ui.console.print("[yellow]Goodbye![/yellow]")
                    break

                elif command == "list":
                    self.list_issues()

                elif command.startswith("analyze"):
                    parts = command.split()
                    if len(parts) < 2:
                        self.ui.console.print("[yellow]Usage: analyze <issue_id or #row>[/yellow]")
                    else:
                        issue_ref = parts[1]
                        # Check if it's a row number (starts with #)
                        if issue_ref.startswith("#"):
                            try:
                                row_num = int(issue_ref[1:])
                                if 1 <= row_num <= len(self.current_issues):
                                    issue = self.current_issues[row_num - 1]
                                    issue_id = str(issue.get("id"))
                                    self.ui.console.print(f"[cyan]Using issue from row {row_num}: {issue_id}[/cyan]")
                                    self.analyze_issue(issue_id)
                                else:
                                    self.ui.console.print(f"[red]Row {row_num} out of range. Run 'list' first.[/red]")
                            except ValueError:
                                self.ui.console.print("[red]Invalid row number format[/red]")
                        else:
                            self.analyze_issue(issue_ref)

                elif command.startswith("filter-version"):
                    parts = command.split()
                    if len(parts) < 2:
                        self.ui.console.print("[yellow]Usage: filter-version <version> [only|started|present|exclude|clear][/yellow]")
                        self.ui.console.print("[dim]Examples:[/dim]")
                        self.ui.console.print("[dim]  filter-version 3.1.19 only      - Issues only in this version[/dim]")
                        self.ui.console.print("[dim]  filter-version 3.1.19 started   - Issues that started in this version[/dim]")
                        self.ui.console.print("[dim]  filter-version 3.1.19 present   - Issues present in this version[/dim]")
                        self.ui.console.print("[dim]  filter-version 3.1.19 exclude   - Issues NOT in this version[/dim]")
                        self.ui.console.print("[dim]  filter-version clear            - Clear version filter[/dim]")
                    else:
                        version = parts[1]
                        mode = parts[2] if len(parts) > 2 else "only"
                        self.filter_by_version(version, mode)

                elif command == "versions":
                    self.show_versions()

                elif command.startswith("filter"):
                    parts = command.split()
                    if len(parts) < 2:
                        self.ui.console.print("[yellow]Usage: filter <unresolved|resolved|muted|all>[/yellow]")
                    else:
                        status = parts[1]
                        self.filter_issues(status)

                elif command.startswith("sort"):
                    parts = command.split()
                    if len(parts) < 2:
                        self.ui.console.print("[yellow]Usage: sort <devices|traces|date> [asc|desc][/yellow]")
                    else:
                        sort_field = parts[1]
                        sort_order = parts[2] if len(parts) > 2 else "desc"
                        self.sort_issues(sort_field, sort_order)

                elif command == "batch-analyze":
                    self.batch_analyze_all()

                elif command.startswith("auto-fix"):
                    parts = command.split()
                    max_issues = int(parts[1]) if len(parts) > 1 else 5
                    self.auto_fix_mode(max_issues)

                elif command.startswith("fix"):
                    parts = command.split()
                    if len(parts) < 2:
                        self.ui.console.print("[yellow]Usage: fix <issue_id or #row>[/yellow]")
                    else:
                        issue_ref = parts[1]
                        self.fix_single_issue(issue_ref)

                elif command == "status":
                    self.show_agent_status()

                elif command == "memory":
                    self.show_memory_stats()

                elif command == "next":
                    self.ui.console.print("[yellow]Pagination not yet implemented[/yellow]")

                elif command == "prev":
                    self.ui.console.print("[yellow]Pagination not yet implemented[/yellow]")

                elif command == "help":
                    self.ui.show_welcome()

                else:
                    self.ui.console.print(f"[red]Unknown command: {command}[/red]")
                    self.ui.console.print("Type 'help' for available commands")

            except KeyboardInterrupt:
                self.ui.console.print("\n[yellow]Use 'quit' to exit[/yellow]")
            except Exception as e:
                self.ui.console.print(f"[red]Error:[/red] {e}")

    def list_issues(self):
        """Fetch and display issues."""
        # Only fetch if we don't have cached issues
        if not self.all_issues:
            self.ui.console.print("[cyan]Fetching issues...[/cyan]")
            self.all_issues = self.memfault_client.get_issues(
                status=self.status_filter,
                limit=100
            )

        # Start with all issues (or status-filtered issues)
        self.current_issues = self.all_issues.copy()

        # Apply version filter if set
        if self.version_filter and self.version_filter != "clear":
            self.current_issues = self.memfault_client.filter_issues_by_version(
                self.current_issues,
                self.version_filter,
                self.version_filter_mode
            )

        # Apply sorting if set
        if self.current_issues and self.sort_by:
            self.current_issues = self._apply_sort(self.current_issues)

        # Build filter info string
        filter_parts = []
        if self.status_filter:
            filter_parts.append(f"status={self.status_filter}")
        if self.version_filter and self.version_filter != "clear":
            filter_parts.append(f"version={self.version_filter} ({self.version_filter_mode})")

        if self.current_issues:
            self.ui.show_issues_table(
                self.current_issues,
                " | ".join(filter_parts) if filter_parts else None,
                sort_info=f"{self.sort_by} ({self.sort_order})" if self.sort_by else None
            )
            self.ui.console.print(f"\n[green]Showing {len(self.current_issues)} of {len(self.all_issues)} issues[/green]")
        else:
            self.ui.console.print("[yellow]No issues match the current filters[/yellow]")

    def filter_issues(self, status: str):
        """Filter issues by status."""
        if status.lower() == "all":
            self.status_filter = None
            self.ui.console.print("[cyan]Showing all issues[/cyan]")
        elif status.lower() in ["unresolved", "resolved", "muted", "merged"]:
            self.status_filter = status.lower()
            self.ui.console.print(f"[cyan]Filtering by status: {status}[/cyan]")
        else:
            self.ui.console.print("[red]Invalid status. Use: unresolved, resolved, muted, merged, or all[/red]")
            return

        # Clear cached issues to re-fetch with new status filter
        self.all_issues = []
        self.list_issues()

    def filter_by_version(self, version: str, mode: str = "only"):
        """Filter issues by firmware version."""
        if version.lower() == "clear":
            self.version_filter = None
            self.version_filter_mode = "only"
            self.ui.console.print("[cyan]Cleared version filter[/cyan]")
            self.list_issues()
            return

        valid_modes = ["only", "started", "present", "exclude"]
        if mode.lower() not in valid_modes:
            self.ui.console.print(f"[red]Invalid mode. Use: {', '.join(valid_modes)}[/red]")
            return

        self.version_filter = version
        self.version_filter_mode = mode.lower()

        mode_descriptions = {
            "only": "only in this version",
            "started": "first appeared in this version",
            "present": "present in this version",
            "exclude": "NOT in this version"
        }

        self.ui.console.print(f"[cyan]Filtering by version: {version} ({mode_descriptions[mode.lower()]})[/cyan]")
        self.list_issues()

    def show_versions(self):
        """Show all firmware versions present in current issues."""
        if not self.current_issues and not self.all_issues:
            self.ui.console.print("[yellow]No issues loaded. Run 'list' first.[/yellow]")
            return

        issues_to_analyze = self.current_issues if self.current_issues else self.all_issues

        # Collect all unique versions
        versions = set()
        for issue in issues_to_analyze:
            first_ver = issue.get('first_software_version', {})
            last_ver = issue.get('last_software_version', {})

            if isinstance(first_ver, dict):
                versions.add(first_ver.get('version', ''))
            if isinstance(last_ver, dict):
                versions.add(last_ver.get('version', ''))

        versions = sorted([v for v in versions if v])

        self.ui.console.print(f"\n[bold cyan]Firmware Versions ({len(versions)} total):[/bold cyan]\n")

        for version in versions:
            # Count issues only in this version
            only_count = len(self.memfault_client.filter_issues_by_version(
                issues_to_analyze, version, "only"
            ))
            # Count issues that started in this version
            started_count = len(self.memfault_client.filter_issues_by_version(
                issues_to_analyze, version, "started"
            ))

            if only_count > 0 or started_count > 0:
                self.ui.console.print(
                    f"  {version:30s} - Only: {only_count:3d} issues | Started: {started_count:3d} issues"
                )
            else:
                self.ui.console.print(f"  {version:30s} [dim]- (present but not first/only)[/dim]")

    def sort_issues(self, sort_field: str, sort_order: str = "desc"):
        """Sort issues by specified field."""
        valid_fields = ["devices", "traces", "date"]
        valid_orders = ["asc", "desc"]

        if sort_field.lower() not in valid_fields:
            self.ui.console.print(f"[red]Invalid sort field. Use: {', '.join(valid_fields)}[/red]")
            return

        if sort_order.lower() not in valid_orders:
            self.ui.console.print(f"[red]Invalid sort order. Use: {', '.join(valid_orders)}[/red]")
            return

        self.sort_by = sort_field.lower()
        self.sort_order = sort_order.lower()
        self.ui.console.print(f"[cyan]Sorting by {self.sort_by} ({self.sort_order})[/cyan]")

        # Re-display current issues with new sort
        if self.current_issues:
            self.current_issues = self._apply_sort(self.current_issues)
            self.ui.show_issues_table(
                self.current_issues,
                self.status_filter,
                sort_info=f"{self.sort_by} ({self.sort_order})"
            )
        else:
            self.ui.console.print("[yellow]No issues to sort. Run 'list' first.[/yellow]")

    def _apply_sort(self, issues: list) -> list:
        """Apply current sort settings to issues."""
        if not self.sort_by:
            return issues

        sort_key_map = {
            "devices": lambda x: x.get("device_count", 0) or 0,
            "traces": lambda x: x.get("trace_count", 0) or 0,
            "date": lambda x: x.get("first_seen", "") or ""
        }

        reverse = (self.sort_order == "desc")

        try:
            return sorted(issues, key=sort_key_map[self.sort_by], reverse=reverse)
        except Exception as e:
            self.ui.console.print(f"[yellow]Warning: Sort failed: {e}[/yellow]")
            return issues

    def analyze_issue(self, issue_id: str):
        """Analyze a specific issue with Claude."""
        self.ui.console.print(f"[cyan]Fetching issue {issue_id}...[/cyan]")

        issue = self.memfault_client.get_issue_details(issue_id)

        if not issue:
            self.ui.console.print(f"[red]Issue {issue_id} not found[/red]")
            return

        # Try to get traces - they might be embedded in the issue or need a different endpoint
        traces = []
        if "traces" in issue:
            traces = issue.get("traces", [])
        else:
            traces = self.memfault_client.get_issue_traces(issue_id, limit=5)

        self.ui.show_issue_details(issue, traces)

        if self.ui.confirm("\nAnalyze this issue with Claude?"):
            self.ui.console.print("[cyan]Analyzing with Claude...[/cyan]")

            analysis = self.claude_analyzer.analyze_issue(issue, traces)
            self.ui.show_analysis(analysis)

            if self.ui.confirm("\nSave analysis to file?"):
                filepath = self.ui.save_analysis(issue_id, issue, analysis)
                self.ui.console.print(f"[green]Analysis saved to: {filepath}[/green]")

    def batch_analyze_all(self):
        """Analyze all issues and store in memory."""
        if not self.memory:
            self.ui.console.print("[red]Agent memory not initialized[/red]")
            return

        self.ui.console.print("[cyan]Fetching all issues...[/cyan]")
        all_issues = self.memfault_client.get_issues(limit=100)

        if not all_issues:
            self.ui.console.print("[yellow]No issues found[/yellow]")
            return

        self.ui.console.print(f"[green]Found {len(all_issues)} issues[/green]")

        if not self.ui.confirm(f"\nAnalyze all {len(all_issues)} issues? This may take a while."):
            return

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=self.ui.console
        ) as progress:
            task = progress.add_task("Analyzing issues...", total=len(all_issues))

            for issue in all_issues:
                issue_id = str(issue.get('id'))
                title = issue.get('title', 'Unknown')

                progress.update(task, description=f"Analyzing {issue_id[:8]}: {title[:40]}")

                # Check if already analyzed
                existing = self.memory.get_issue(issue_id)
                if existing and existing.analysis_file:
                    progress.update(task, advance=1)
                    continue

                # Get detailed issue data
                detailed_issue = self.memfault_client.get_issue_details(issue_id)
                if not detailed_issue:
                    progress.update(task, advance=1)
                    continue

                traces = self.memfault_client.get_issue_traces(issue_id, limit=5)

                # Analyze with Claude
                analysis = self.claude_analyzer.analyze_issue(detailed_issue, traces)

                # Save analysis
                filepath = self.ui.save_analysis(issue_id, detailed_issue, analysis)

                # Store in memory
                self.memory.store_issue(detailed_issue, filepath)
                self.memory.update_fix_status(issue_id, FixStatus.ANALYZED)

                progress.update(task, advance=1)

        self.ui.console.print(f"\n[green]✓ Batch analysis complete![/green]")
        self.show_memory_stats()

    def auto_fix_mode(self, max_issues: int = 5):
        """Autonomous mode: attempt to fix issues automatically."""
        if not self.agent:
            self.ui.console.print("[red]Autonomous agent not available[/red]")
            self.ui.console.print("[yellow]Please configure SOURCE_CODE_PATH in .env[/yellow]")
            return

        self.ui.console.print(f"[bold cyan]Autonomous Fix Mode[/bold cyan]")
        self.ui.console.print(f"Safety mode: {self.agent.describe_safety_mode()}")
        self.ui.console.print(f"Will process up to {max_issues} issues\n")

        # Get analyzed issues that haven't been fixed
        analyzed = self.memory.get_issues_by_status(FixStatus.ANALYZED)

        if not analyzed:
            self.ui.console.print("[yellow]No analyzed issues ready for fixing[/yellow]")
            self.ui.console.print("[cyan]Run 'batch-analyze' first[/cyan]")
            return

        # Sort by impact (device count)
        analyzed.sort(key=lambda x: x.device_count, reverse=True)
        to_fix = analyzed[:max_issues]

        self.ui.console.print(f"[green]Found {len(analyzed)} analyzed issues[/green]")
        self.ui.console.print(f"[cyan]Will process top {len(to_fix)} by impact:[/cyan]\n")

        for i, record in enumerate(to_fix, 1):
            self.ui.console.print(f"  {i}. {record.title} ({record.device_count} devices)")

        if not self.ui.confirm("\nProceed with fix draft generation?"):
            return

        # Generate drafts or apply fixes depending on the configured safety mode.
        completed_count = 0
        for record in to_fix:
            # Load analysis
            if not record.analysis_file:
                continue

            with open(record.analysis_file, 'r') as f:
                analysis = f.read()

            # Get full issue data
            issue = self.memfault_client.get_issue_details(record.issue_id)
            if not issue:
                continue

            # Attempt fix
            success = self.agent.attempt_fix(issue, analysis)
            if success:
                completed_count += 1

        self.ui.console.print(f"\n[bold green]Autonomous run complete![/bold green]")
        self.ui.console.print(f"Completed workflows: {completed_count}/{len(to_fix)}")
        self.show_memory_stats()

    def show_agent_status(self):
        """Show current agent status."""
        if not self.memory:
            self.ui.console.print("[red]Agent memory not initialized[/red]")
            return

        self.ui.console.print("\n[bold cyan]Agent Status[/bold cyan]\n")

        # Get status breakdown
        for status in FixStatus:
            issues = self.memory.get_issues_by_status(status)
            if issues:
                self.ui.console.print(f"  {status.value:20s}: {len(issues):3d} issues")

    def show_memory_stats(self):
        """Show statistics from agent memory."""
        if not self.memory:
            self.ui.console.print("[red]Agent memory not initialized[/red]")
            return

        stats = self.memory.get_statistics()

        self.ui.console.print("\n[bold cyan]Agent Memory Statistics[/bold cyan]\n")
        self.ui.console.print(f"  Total Issues:      {stats['total_issues']}")
        self.ui.console.print(f"  Total Attempts:    {stats['total_attempts']}")
        self.ui.console.print(f"  Successful Fixes:  {stats['successful_fixes']}")

        if stats['total_issues'] > 0:
            success_rate = (stats['successful_fixes'] / stats['total_issues']) * 100
            self.ui.console.print(f"  Success Rate:      {success_rate:.1f}%")

        self.ui.console.print("\n[bold]By Status:[/bold]")
        for status, count in stats.get('by_status', {}).items():
            self.ui.console.print(f"  {status:20s}: {count}")

    def fix_single_issue(self, issue_ref: str):
        """Attempt to fix a single issue by ID or row number."""
        if not self.agent:
            self.ui.console.print("[red]Autonomous agent not available[/red]")
            self.ui.console.print("[yellow]Please configure SOURCE_CODE_PATH in .env[/yellow]")
            return

        # Resolve issue ID from row number if needed
        issue_id = None
        if issue_ref.startswith("#"):
            try:
                row_num = int(issue_ref[1:])
                if 1 <= row_num <= len(self.current_issues):
                    issue = self.current_issues[row_num - 1]
                    issue_id = str(issue.get("id"))
                    self.ui.console.print(f"[cyan]Using issue from row {row_num}: {issue_id}[/cyan]")
                else:
                    self.ui.console.print(f"[red]Row {row_num} out of range. Run 'list' first.[/red]")
                    return
            except ValueError:
                self.ui.console.print("[red]Invalid row number format[/red]")
                return
        else:
            issue_id = issue_ref

        # Check if issue exists in memory
        issue_record = self.memory.get_issue(issue_id)

        # If not in memory or not analyzed, analyze it first
        if not issue_record or not issue_record.analysis_file:
            self.ui.console.print(f"[cyan]Issue {issue_id} not yet analyzed. Analyzing first...[/cyan]")

            # Fetch issue details
            issue = self.memfault_client.get_issue_details(issue_id)
            if not issue:
                self.ui.console.print(f"[red]Issue {issue_id} not found[/red]")
                return

            # Get traces
            traces = self.memfault_client.get_issue_traces(issue_id, limit=5)

            # Analyze with Claude
            self.ui.console.print("[cyan]Analyzing with Claude...[/cyan]")
            analysis = self.claude_analyzer.analyze_issue(issue, traces)

            # Save analysis
            filepath = self.ui.save_analysis(issue_id, issue, analysis)
            self.ui.console.print(f"[green]Analysis saved to: {filepath}[/green]")

            # Store in memory
            self.memory.store_issue(issue, filepath)
            self.memory.update_fix_status(issue_id, FixStatus.ANALYZED)

            issue_record = self.memory.get_issue(issue_id)

        # Show issue info
        self.ui.console.print(f"\n[bold cyan]Preparing fix workflow for issue: {issue_id}[/bold cyan]")
        self.ui.console.print(f"[bold]{issue_record.title}[/bold]")
        self.ui.console.print(f"Affected: {issue_record.device_count} devices, {issue_record.trace_count} traces")
        self.ui.console.print(f"Safety mode: {self.agent.describe_safety_mode()}")

        if issue_record.fix_status in [FixStatus.COMPLETED.value, FixStatus.BRANCH_PUSHED.value]:
            self.ui.console.print(f"[yellow]⚠ This issue has status: {issue_record.fix_status}[/yellow]")
            if not self.ui.confirm("Attempt to fix again anyway?"):
                return

        # Confirm before proceeding
        if not self.ui.confirm("\nProceed with fix draft generation?"):
            return

        # Load analysis
        if not issue_record.analysis_file:
            self.ui.console.print("[red]No analysis file found for this issue[/red]")
            return

        with open(issue_record.analysis_file, 'r') as f:
            analysis = f.read()

        # Get full issue data
        issue = self.memfault_client.get_issue_details(issue_id)
        if not issue:
            self.ui.console.print(f"[red]Failed to fetch issue details[/red]")
            return

        # Attempt fix
        success = self.agent.attempt_fix(issue, analysis)

        if success:
            self.ui.console.print(f"\n[bold green]✓ Fix workflow completed for issue {issue_id}.[/bold green]")
        else:
            self.ui.console.print(f"\n[yellow]⚠ Fix workflow did not complete[/yellow]")
            self.ui.console.print(f"[cyan]Check analysis file: {issue_record.analysis_file}[/cyan]")


def main():
    """Entry point."""
    app = MemfaultAnalyzer()
    app.run()


if __name__ == "__main__":
    main()

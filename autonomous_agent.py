"""Autonomous agent for analyzing and fixing Memfault issues."""
import json
import queue
import shlex
import subprocess
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from anthropic import Anthropic

from agent_memory import AgentMemory, FixStatus
from config import Config


console = Console()


class AutonomousAgent:
    """Agent that autonomously analyzes and fixes issues."""

    def __init__(
        self,
        memory: AgentMemory,
        source_path: Path,
        anthropic_client: Anthropic,
        model: Optional[str] = None,
        ai_client: Optional[str] = None,
    ):
        self.memory = memory
        self.source_path = source_path
        self.client = anthropic_client
        self.ai_client = ai_client or Config.AI_CLIENT
        if self.ai_client != "anthropic":
            raise ValueError(f"Unsupported AI_CLIENT: {self.ai_client}")
        self.model = model or Config.AI_MODEL
        self._shell_proc = None
        self._sentinel_counter = 0
        self.run_git_commands = Config.AUTONOMOUS_RUN_GIT_COMMANDS
        self.apply_fixes = Config.AUTONOMOUS_APPLY_FIXES
        self.build_fixes = Config.AUTONOMOUS_BUILD_FIXES
        self.commit_fixes = Config.AUTONOMOUS_COMMIT_FIXES

    def describe_safety_mode(self) -> str:
        """Return a short description of autonomous fix safety settings."""
        if not self.apply_fixes:
            return "dry-run: generate fix drafts only"

        enabled = ["apply edits"]
        if self.run_git_commands:
            enabled.append("run AI git strategy")
        if self.build_fixes:
            enabled.append("build")
        if self.commit_fixes:
            enabled.append("commit")
        return "mutating: " + ", ".join(enabled)

    # ── Persistent workspace shell ───────────────────────────────

    def _ensure_workspace_shell(self):
        """Start a persistent zsh session in the workspace with direnv/nix env loaded once."""
        if self._shell_proc is not None and self._shell_proc.poll() is None:
            return

        console.print("[cyan]Starting workspace shell (loading nix env)...[/cyan]")
        self._shell_proc = subprocess.Popen(
            ['zsh'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(self.source_path),
            text=True,
            bufsize=1,
        )
        self._sentinel_counter = 0

        # Load direnv/nix environment into this shell session
        rc, output = self._shell_exec(
            'eval "$(direnv export zsh 2>&1)"',
            timeout=120
        )
        if rc == 0:
            console.print("[green]✓ Workspace shell ready (nix env loaded)[/green]")
        else:
            console.print(f"[yellow]direnv export returned rc={rc}, continuing anyway[/yellow]")
            if output.strip():
                console.print(f"[dim]{output.strip()[:300]}[/dim]")

    def _shell_exec(self, cmd_str: str, timeout: int = 60) -> Tuple[int, str]:
        """Execute a raw command string in the persistent shell.

        Returns (returncode, combined_output).
        Uses a sentinel pattern to delimit command output.
        """
        self._sentinel_counter += 1
        sentinel = f"__MFA_DONE_{self._sentinel_counter}__"

        self._shell_proc.stdin.write(f'{cmd_str}\necho "{sentinel}_RC_$?"\n')
        self._shell_proc.stdin.flush()

        result_q: queue.Queue[Tuple[int, str]] = queue.Queue()
        lines: List[str] = []

        def _reader():
            while True:
                line = self._shell_proc.stdout.readline()
                if not line:
                    result_q.put((1, ''.join(lines)))
                    return
                if sentinel in line:
                    try:
                        rc = int(line.strip().split('_RC_')[-1])
                    except (IndexError, ValueError):
                        rc = 1
                    result_q.put((rc, ''.join(lines)))
                    return
                lines.append(line)

        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        t.join(timeout=timeout)

        if t.is_alive():
            return 1, f"Command timed out after {timeout}s"

        return result_q.get()

    def close_workspace_shell(self):
        """Close the persistent workspace shell."""
        if self._shell_proc and self._shell_proc.poll() is None:
            try:
                self._shell_proc.stdin.write('exit\n')
                self._shell_proc.stdin.flush()
                self._shell_proc.wait(timeout=5)
            except Exception:
                self._shell_proc.kill()
            self._shell_proc = None

    def run_in_workspace(self, *args: str, timeout: int = 60) -> Tuple[int, str, str]:
        """Run a command in the persistent workspace shell (nix env loaded once)."""
        self._ensure_workspace_shell()
        cmd_str = ' '.join(shlex.quote(a) for a in args)
        console.print(f"[dim]$ {cmd_str}[/dim]")

        returncode, output = self._shell_exec(cmd_str, timeout=timeout)
        # stderr is merged into stdout; return empty string for interface compat
        return returncode, output, ""

    def _ensure_clean_worktree(self) -> bool:
        """Require a clean worktree before mutating source files or git state."""
        returncode, stdout, _ = self.run_in_workspace('git', 'status', '--porcelain')
        if returncode != 0:
            console.print(f"[red]Could not inspect git status: {stdout.strip()}[/red]")
            return False

        if stdout.strip():
            console.print("[red]Refusing to mutate a dirty worktree.[/red]")
            console.print("[yellow]Commit, stash, or move local changes before enabling autonomous writes.[/yellow]")
            preview = "\n".join(stdout.splitlines()[:20])
            console.print(f"[dim]{preview}[/dim]")
            return False

        return True

    def _validate_strategy_command(self, cmd_str: str) -> Tuple[Optional[List[str]], Optional[str]]:
        """Validate an AI-proposed command before execution."""
        try:
            parts = shlex.split(cmd_str)
        except ValueError as e:
            return None, f"Could not parse command {cmd_str!r}: {e}"

        if not parts:
            return None, "Empty command"

        allowed_commands = {"git", "west", "cd"}
        if parts[0] not in allowed_commands:
            return None, f"Command {parts[0]!r} is not allowed"

        shell_tokens = {";", "&&", "||", "|", ">", ">>", "<"}
        if any(part in shell_tokens for part in parts):
            return None, f"Shell control token found in command {cmd_str!r}"

        return parts, None

    def _resolve_edit_path(self, filepath: str) -> Tuple[Optional[Path], Optional[str]]:
        """Resolve and validate an edit path under source_path."""
        if not filepath:
            return None, "missing file path"

        candidate = Path(filepath)
        if candidate.is_absolute():
            return None, f"absolute paths are not allowed: {filepath}"
        if ".." in candidate.parts:
            return None, f"parent directory traversal is not allowed: {filepath}"

        root = self.source_path.resolve()
        resolved = (root / candidate).resolve()

        try:
            resolved.relative_to(root)
        except ValueError:
            return None, f"path escapes source root: {filepath}"

        if not resolved.is_file():
            return None, f"file does not exist: {filepath}"

        return resolved, None

    def save_fix_draft(
        self,
        issue_id: str,
        fix_data: Dict,
        strategy: Dict[str, object],
        errors: Optional[List[str]] = None,
    ) -> Path:
        """Save a reviewable fix draft without modifying source files."""
        draft_dir = Config.OUTPUT_DIR / "fix_drafts"
        draft_dir.mkdir(parents=True, exist_ok=True)

        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", issue_id)[:80]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        draft_path = draft_dir / f"fix_{safe_id}_{timestamp}.md"

        edits = fix_data.get('edits', [])
        commands = strategy.get('commands', [])
        target_repo = strategy.get('target_repo', '')
        build_dir = strategy.get('build_dir', '')

        lines = [
            f"# Fix Draft: {issue_id}",
            "",
            "This draft was generated for review. Source files are modified only when explicit safety gates are enabled.",
            "",
            "## Safety Mode",
            "",
            f"- {self.describe_safety_mode()}",
            "",
            "## Git Strategy",
            "",
            f"- Target repo: {target_repo or 'not specified'}",
            f"- Build dir: {build_dir or 'not specified'}",
            "",
        ]

        if commands:
            lines.extend(["Proposed commands:", ""])
            lines.extend(f"- `{cmd}`" for cmd in commands)
            lines.append("")

        if errors:
            lines.extend(["## Notes", ""])
            lines.extend(f"- {err}" for err in errors)
            lines.append("")

        lines.extend([
            "## Summary",
            "",
            fix_data.get('summary', 'No summary provided.'),
            "",
            "## Proposed Edits",
            "",
        ])

        if not edits:
            lines.append("No edits were generated.")
        else:
            for index, edit in enumerate(edits, 1):
                lines.extend([
                    f"### {index}. `{edit.get('file', '')}`",
                    "",
                    edit.get('description', ''),
                    "",
                    "Existing code:",
                    "",
                    "```",
                    edit.get('old_code', ''),
                    "```",
                    "",
                    "Replacement code:",
                    "",
                    "```",
                    edit.get('new_code', ''),
                    "```",
                    "",
                ])

        draft_path.write_text("\n".join(lines), encoding="utf-8")
        console.print(f"[green]✓ Fix draft saved to {draft_path}[/green]")
        return draft_path

    def load_agent_context(self) -> Optional[str]:
        """Load AGENT.md from the workspace if it exists."""
        agent_md = self.source_path / "AGENT.md"
        if agent_md.exists():
            try:
                content = agent_md.read_text()
                console.print("[green]✓ Loaded AGENT.md from workspace[/green]")
                return content
            except Exception as e:
                console.print(f"[yellow]Warning: Could not read AGENT.md: {e}[/yellow]")
        else:
            console.print(f"[yellow]No AGENT.md found at {agent_md}[/yellow]")
        return None

    def discover_workspace(self) -> Dict[str, Optional[str]]:
        """Discover the workspace structure by reading AGENT.md, running west list,
        locating git remotes, and finding buildable directories."""
        console.print("\n[bold cyan]Discovering workspace...[/bold cyan]")

        # 1. Read AGENT.md
        agent_md = self.load_agent_context()

        # 2. Run west list to understand the multi-repo structure
        west_list = None
        console.print("[cyan]Running west list...[/cyan]")
        returncode, stdout, stderr = self.run_in_workspace('west', 'list')
        if returncode == 0:
            west_list = stdout.strip()
            console.print(f"[green]✓ west list returned {len(west_list.splitlines())} repos[/green]")
        else:
            console.print(f"[yellow]west list failed: {stderr.strip()}[/yellow]")

        # 3. Collect git remotes from repos in the workspace
        git_remotes = None
        console.print("[cyan]Collecting git remotes...[/cyan]")
        returncode, stdout, stderr = self.run_in_workspace(
            'west', 'forall', '-c', 'echo "=== $WEST_PROJECT_NAME ===" && git remote -v'
        )
        if returncode == 0:
            git_remotes = stdout.strip()
            console.print("[green]✓ Collected git remotes[/green]")
        else:
            console.print(f"[yellow]Failed to collect git remotes: {stderr.strip()}[/yellow]")

        # 4. Find prj.conf and CMakeLists.txt (buildable directories)
        build_dirs = None
        console.print("[cyan]Locating buildable directories (prj.conf)...[/cyan]")
        returncode, stdout, stderr = self.run_in_workspace(
            'find', '.', '-name', 'prj.conf', '-not', '-path', '*/build/*'
        )
        if returncode == 0 and stdout.strip():
            build_dirs = stdout.strip()
            console.print(f"[green]✓ Found {len(build_dirs.splitlines())} prj.conf files[/green]")
        else:
            console.print("[yellow]No prj.conf files found[/yellow]")

        return {
            'agent_md': agent_md,
            'west_list': west_list,
            'git_remotes': git_remotes,
            'build_dirs': build_dirs,
        }

    def ask_agent_git_strategy(
        self,
        workspace_context: Dict[str, Optional[str]],
        issue_id: str,
        issue_title: str
    ) -> Dict[str, object]:
        """Ask the AI agent which git commands to run to create a fix branch.

        Returns a dict with 'commands' (list of shell strings),
        'build_dir' (path to directory with prj.conf), and
        'target_repo' (name/path of the repo for the fix).
        """
        console.print("[cyan]Asking AI agent for git strategy...[/cyan]")

        agent_md = workspace_context.get('agent_md') or '(not available)'
        west_list = workspace_context.get('west_list') or '(not available)'
        git_remotes = workspace_context.get('git_remotes') or '(not available)'
        build_dirs = workspace_context.get('build_dirs') or '(not available)'

        prompt = f"""You are an autonomous agent working in a west-based multi-repo workspace.
Your task is to determine the correct git commands to create a fix branch for a bug,
and navigate to the correct build directory.

# Workspace AGENT.md
{agent_md}

# west list output
{west_list}

# Git remotes per repo
IMPORTANT: The remote is NOT always "origin". Use the actual remote name shown below
when running fetch/pull/push commands.
{git_remotes}

# Buildable directories (prj.conf locations)
These are directories containing prj.conf and CMakeLists.txt where `west build` can run:
{build_dirs}

# Issue to fix
- ID: {issue_id}
- Title: {issue_title}

# Instructions
Based on the AGENT.md instructions and the west workspace structure, provide the exact
shell commands to run (in order) to:

1. **Fetch latest from the correct remote** — use the actual remote name from the git
   remotes listed above (do NOT assume "origin")
2. **Create a fix branch** in the correct repo for this issue
3. **Navigate (cd) to the build directory** — the directory containing prj.conf and
   CMakeLists.txt where one can run `west build`

Think about:
- Which repo should the fix go into? (based on the issue title/context)
- What is the correct git remote name for that repo?
- How to create a branch in that repo (the AGENT.md may have specific instructions)
- Which prj.conf directory is relevant for building/testing the fix?

Return your answer as a JSON object with these fields:
- "commands": a list of shell command strings to execute in order
- "target_repo": the name/path of the repo where the fix should go
- "build_dir": the path to the directory with prj.conf where `west build` should run
- "reasoning": a brief explanation of why you chose this repo, remote, and build directory

Return ONLY the JSON object, no markdown fences or extra text.
"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()

            # Strip markdown fences if present
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                lines = [l for l in lines if not l.startswith("```")]
                response_text = "\n".join(lines)

            result = json.loads(response_text)
            commands = result.get('commands', [])
            target_repo = result.get('target_repo', 'unknown')
            build_dir = result.get('build_dir', '')
            reasoning = result.get('reasoning', '')

            console.print(f"[green]✓ AI strategy: target repo = {target_repo}[/green]")
            if build_dir:
                console.print(f"[green]✓ Build directory: {build_dir}[/green]")
            console.print(f"[dim]{reasoning}[/dim]")
            console.print(f"[cyan]Commands to run ({len(commands)}):[/cyan]")
            for cmd in commands:
                console.print(f"  [dim]$ {cmd}[/dim]")

            return {
                'commands': commands,
                'build_dir': build_dir,
                'target_repo': target_repo,
            }

        except json.JSONDecodeError as e:
            console.print(f"[yellow]Could not parse AI response as JSON: {e}[/yellow]")
            console.print(f"[dim]Raw response: {response_text[:500]}[/dim]")
            return {'commands': [], 'build_dir': '', 'target_repo': ''}
        except Exception as e:
            console.print(f"[red]Error asking AI for git strategy: {e}[/red]")
            return {'commands': [], 'build_dir': '', 'target_repo': ''}

    def generate_fix(
        self,
        issue: Dict,
        analysis: str,
        workspace_context: Optional[Dict[str, Optional[str]]] = None,
        errors: Optional[List[str]] = None
    ) -> Optional[Dict]:
        """
        Use Claude to generate structured code edits.

        Returns a dict with:
          - 'edits': list of {file, description, old_code, new_code}
          - 'summary': brief description of all changes
          - 'raw': the raw response text
        """
        console.print("[cyan]Generating fix with Claude...[/cyan]")

        agent_context = None
        west_list = None
        if workspace_context:
            agent_context = workspace_context.get('agent_md')
            west_list = workspace_context.get('west_list')
        else:
            agent_context = self.load_agent_context()

        error_section = ""
        if errors:
            error_section = "\n# Errors Encountered\nThe following errors occurred during the fix process. Take them into account:\n"
            for err in errors:
                error_section += f"- {err}\n"

        agent_section = ""
        if agent_context:
            agent_section = f"\n# Project Context (from AGENT.md)\n{agent_context}\n"

        workspace_section = ""
        if west_list:
            workspace_section = f"\n# Workspace Repos (west list)\n```\n{west_list}\n```\n"

        prompt = f"""You are an autonomous firmware engineering agent fixing a real embedded systems issue.
{agent_section}{workspace_section}
# Issue Details
- **ID**: {issue.get('id')}
- **Title**: {issue.get('title')}
- **Message**: {issue.get('message')}
- **Affected**: {issue.get('device_count')} devices, {issue.get('trace_count')} traces

# Previous Analysis
{analysis}
{error_section}
# Task
Generate concrete code changes to fix this issue. For each change you MUST provide
the **exact existing lines** that need to be replaced and the **replacement code**.

Return ONLY a JSON object (no markdown fences, no extra text) with this structure:

{{
  "edits": [
    {{
      "file": "relative/path/to/file.c",
      "description": "what this change does",
      "old_code": "exact existing lines to find in the file",
      "new_code": "replacement code"
    }}
  ],
  "summary": "brief description of all changes"
}}

Rules:
- "old_code" must be a verbatim substring of the current file content (enough context to be unique)
- "new_code" is the replacement for that exact substring
- Use relative paths from the workspace root
- Provide compilable, correct C code
- Keep changes minimal — only what is needed to fix the issue
"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}]
            )

            raw = response.content[0].text.strip()

            # Strip markdown fences if present
            text = raw
            if text.startswith("```"):
                lines = text.split("\n")
                lines = [l for l in lines if not l.startswith("```")]
                text = "\n".join(lines)

            result = json.loads(text)
            edits = result.get('edits', [])
            summary = result.get('summary', '')

            console.print(f"[green]✓ Generated {len(edits)} edit(s): {summary}[/green]")
            for i, edit in enumerate(edits):
                console.print(f"  [dim]{i+1}. {edit.get('file')}: {edit.get('description')}[/dim]")

            return {'edits': edits, 'summary': summary, 'raw': raw}

        except json.JSONDecodeError as e:
            console.print(f"[yellow]Could not parse fix response as JSON: {e}[/yellow]")
            console.print(f"[dim]Raw response: {raw[:500]}[/dim]")
            return None
        except Exception as e:
            console.print(f"[red]Error generating fix: {e}[/red]")
            return None

    def apply_edits(self, edits: List[Dict[str, str]]) -> Tuple[bool, List[str], Dict[Path, str]]:
        """Apply structured edits to files in the workspace.

        For each edit, reads the file, finds old_code, replaces with new_code,
        and writes back.

        Returns (all_ok, list_of_error_messages, original_content_by_path).
        """
        errors: List[str] = []
        planned: List[Tuple[Path, str, str]] = []

        for i, edit in enumerate(edits):
            filepath = edit.get('file', '')
            old_code = edit.get('old_code', '')
            new_code = edit.get('new_code', '')
            desc = edit.get('description', '')

            console.print(f"[cyan]Applying edit {i+1}/{len(edits)}: {filepath} — {desc}[/cyan]")

            if not filepath or not old_code:
                errors.append(f"Edit {i+1}: missing file or old_code")
                continue

            resolved, path_error = self._resolve_edit_path(filepath)
            if path_error:
                errors.append(f"Edit {i+1}: {path_error}")
                continue

            try:
                content = resolved.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                errors.append(f"Edit {i+1}: {filepath} is not UTF-8 text")
                continue
            except OSError as e:
                errors.append(f"Edit {i+1}: cannot read {filepath}: {e}")
                continue

            occurrences = content.count(old_code)
            if occurrences == 0:
                errors.append(
                    f"Edit {i+1}: old_code not found in {filepath}. "
                    f"First 80 chars of old_code: {old_code[:80]!r}"
                )
                continue
            if occurrences > 1:
                errors.append(
                    f"Edit {i+1}: old_code is not unique in {filepath} "
                    f"({occurrences} matches)"
                )
                continue

            new_content = content.replace(old_code, new_code, 1)
            planned.append((resolved, content, new_content))

        if errors:
            for err in errors:
                console.print(f"[red]  ✗ {err}[/red]")
            return False, errors, {}

        originals: Dict[Path, str] = {}
        for resolved, old_content, new_content in planned:
            if resolved not in originals:
                originals[resolved] = old_content
            try:
                resolved.write_text(new_content, encoding="utf-8")
            except OSError as e:
                errors.append(f"Failed to write {resolved}: {e}")

        if errors:
            self.restore_originals(originals)
            for err in errors:
                console.print(f"[red]  ✗ {err}[/red]")
            return False, errors, {}

        console.print(f"[green]✓ All {len(edits)} edit(s) applied[/green]")
        return True, [], originals

    def restore_originals(self, originals: Dict[Path, str]):
        """Restore files changed by apply_edits."""
        for path, content in originals.items():
            try:
                path.write_text(content, encoding="utf-8")
                console.print(f"[yellow]Restored {path.relative_to(self.source_path.resolve())}[/yellow]")
            except Exception as e:
                console.print(f"[red]Could not restore {path}: {e}[/red]")

    def build_project(self, build_dir: str) -> Tuple[bool, str]:
        """Run `west build` in the given build directory via the persistent shell.

        Returns (success, build_output).
        """
        console.print(f"[cyan]Building project in {build_dir}...[/cyan]")

        self._ensure_workspace_shell()

        # cd into build_dir and run west build (timeout 5 min)
        cmd = f'cd {shlex.quote(build_dir)} && west build'
        rc, output = self._shell_exec(cmd, timeout=300)

        if rc == 0:
            console.print("[green]✓ Build successful[/green]")
        else:
            console.print(f"[red]Build failed (rc={rc})[/red]")
            # Show last 30 lines of output for context
            tail = "\n".join(output.splitlines()[-30:])
            console.print(f"[dim]{tail}[/dim]")

        return rc == 0, output

    def revise_fix(
        self,
        issue: Dict,
        previous_edits: List[Dict[str, str]],
        build_errors: str,
        workspace_context: Optional[Dict[str, Optional[str]]] = None,
    ) -> Optional[Dict]:
        """Send the previous fix + build errors to Claude and ask for revised edits.

        Returns the same structure as generate_fix().
        """
        console.print("[cyan]Asking Claude to revise fix based on build errors...[/cyan]")

        agent_context = ""
        if workspace_context and workspace_context.get('agent_md'):
            agent_context = f"\n# Project Context (from AGENT.md)\n{workspace_context['agent_md']}\n"

        edits_json = json.dumps(previous_edits, indent=2)

        # Keep only last 200 lines of build output to stay within token limits
        error_tail = "\n".join(build_errors.splitlines()[-200:])

        prompt = f"""You are an autonomous firmware engineering agent. Your previous code fix
failed to compile. Revise the fix so it builds successfully.
{agent_context}
# Issue
- **Title**: {issue.get('title')}
- **Message**: {issue.get('message')}

# Previous Edits (failed to build)
```json
{edits_json}
```

# Build Error Output
```
{error_tail}
```

# Task
Analyze the build errors and produce a corrected set of edits.
Return ONLY a JSON object (no markdown fences, no extra text):

{{
  "edits": [
    {{
      "file": "relative/path/to/file.c",
      "description": "what this change does",
      "old_code": "exact existing lines to find in the file (from the ORIGINAL, pre-edit source)",
      "new_code": "corrected replacement code"
    }}
  ],
  "summary": "brief description of revisions"
}}

IMPORTANT: "old_code" must match the ORIGINAL source files (before any edits),
because changes are reverted before each retry.
"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}]
            )

            raw = response.content[0].text.strip()
            text = raw
            if text.startswith("```"):
                lines = text.split("\n")
                lines = [l for l in lines if not l.startswith("```")]
                text = "\n".join(lines)

            result = json.loads(text)
            edits = result.get('edits', [])
            summary = result.get('summary', '')

            console.print(f"[green]✓ Revised fix: {len(edits)} edit(s) — {summary}[/green]")
            return {'edits': edits, 'summary': summary, 'raw': raw}

        except json.JSONDecodeError as e:
            console.print(f"[yellow]Could not parse revised fix as JSON: {e}[/yellow]")
            return None
        except Exception as e:
            console.print(f"[red]Error revising fix: {e}[/red]")
            return None

    def commit_changes(self, issue_id: str, message: str, files: List[Path]) -> Optional[str]:
        """Commit the changes using the persistent workspace shell."""
        console.print("[cyan]Committing changes...[/cyan]")

        self._ensure_workspace_shell()

        if not files:
            console.print("[yellow]No changed files to commit[/yellow]")
            return None

        root = self.source_path.resolve()
        relative_files = [str(path.resolve().relative_to(root)) for path in files]

        # Stage only files changed by this agent.
        returncode, stdout, _ = self.run_in_workspace('git', 'add', *relative_files)
        if returncode != 0:
            console.print(f"[red]Failed to stage changes: {stdout.strip()}[/red]")
            return None

        # Commit
        commit_message = (
            f"Fix issue {issue_id[:8]}: {message}\n\n"
            "This fix was automatically generated by the Memfault AI Agent.\n\n"
            f"Issue ID: {issue_id}"
        )
        returncode, stdout, _ = self.run_in_workspace('git', 'commit', '-m', commit_message)
        if returncode != 0:
            console.print(f"[red]Failed to commit: {stdout.strip()}[/red]")
            return None

        # Get commit SHA
        returncode, stdout, _ = self.run_in_workspace('git', 'rev-parse', 'HEAD')
        if returncode == 0:
            commit_sha = stdout.strip()
            console.print(f"[green]✓ Committed: {commit_sha[:8]}[/green]")
            return commit_sha

        return None

    def push_branch(self, branch_name: str) -> bool:
        """Push the branch to remote using the persistent workspace shell."""
        console.print(f"[cyan]Pushing branch {branch_name}...[/cyan]")

        self._ensure_workspace_shell()
        returncode, stdout, _ = self.run_in_workspace('git', 'push', '-u', 'origin', branch_name)
        if returncode != 0:
            console.print(f"[red]Failed to push: {stdout.strip()}[/red]")
            return False

        console.print("[green]✓ Branch pushed successfully[/green]")
        return True

    def attempt_fix(self, issue: Dict, analysis: str) -> bool:
        """
        Attempt to fix a single issue end-to-end.

        Flow:
        1. Discover workspace
        2. Ask AI for git strategy (commands, build_dir, target_repo)
        3. Generate structured fix (JSON edits)
        4. Save a reviewable fix draft
        5. Optionally apply/build/commit only when explicit safety flags are enabled
        """
        issue_id = str(issue.get('id'))
        issue_title = issue.get('title', 'Unknown')
        errors: List[str] = []
        max_build_attempts = 3

        console.print(f"\n[bold cyan]{'='*60}[/bold cyan]")
        console.print(f"[bold]Attempting to fix issue: {issue_id}[/bold]")
        console.print(f"[bold]{issue_title}[/bold]")
        console.print(f"[cyan]Safety mode: {self.describe_safety_mode()}[/cyan]")
        console.print(f"[bold cyan]{'='*60}[/bold cyan]\n")

        self.memory.update_fix_status(issue_id, FixStatus.FIX_IN_PROGRESS)

        try:
            # Step 1: Discover workspace
            workspace_context = self.discover_workspace()

            # Step 2: Ask AI for git strategy
            strategy = self.ask_agent_git_strategy(
                workspace_context, issue_id, issue_title
            )
            git_commands = strategy.get('commands', [])
            build_dir = strategy.get('build_dir', '')
            target_repo = strategy.get('target_repo', '')

            # Step 3: Optionally execute AI-recommended git commands
            if git_commands:
                if self.run_git_commands:
                    if not self._ensure_clean_worktree():
                        raise Exception("Worktree is not clean; refusing to run git strategy")

                    console.print("\n[cyan]Executing validated git strategy...[/cyan]")
                    for cmd_str in git_commands:
                        parts, validation_error = self._validate_strategy_command(cmd_str)
                        if validation_error:
                            err_msg = f"Rejected command `{cmd_str}`: {validation_error}"
                            console.print(f"[yellow]{err_msg}[/yellow]")
                            errors.append(err_msg)
                            continue

                        returncode, stdout, _ = self.run_in_workspace(*parts)
                        if returncode != 0:
                            err_msg = f"Command failed: `{cmd_str}` — {stdout.strip()}"
                            console.print(f"[yellow]{err_msg}[/yellow]")
                            errors.append(err_msg)
                        else:
                            console.print(f"[green]✓ {cmd_str}[/green]")
                            if stdout.strip():
                                console.print(f"[dim]{stdout.strip()[:200]}[/dim]")
                else:
                    console.print("[yellow]Dry-run: not executing AI-proposed git commands.[/yellow]")
                    errors.append("Dry-run: git strategy was not executed")
            else:
                errors.append("AI agent returned no git commands — generating fix without branch")

            # Step 4: Generate structured fix
            fix_data = self.generate_fix(
                issue, analysis,
                workspace_context=workspace_context,
                errors=errors if errors else None
            )
            if not fix_data or not fix_data.get('edits'):
                raise Exception("Failed to generate fix (no edits returned)")

            edits = fix_data['edits']
            summary = fix_data.get('summary', issue_title)
            raw_content = fix_data.get('raw', json.dumps(edits, indent=2))
            draft_path = self.save_fix_draft(issue_id, fix_data, strategy, errors if errors else None)

            issue_record = self.memory.get_issue(issue_id)
            if issue_record and issue_record.analysis_file:
                analysis_path = Path(issue_record.analysis_file)
                with open(analysis_path, 'a') as f:
                    f.write("\n\n## Automated Fix Draft\n\n")
                    f.write(f"Draft saved to: {draft_path}\n\n")
                    f.write(raw_content)

            if not self.apply_fixes:
                self.memory.update_fix_status(
                    issue_id,
                    FixStatus.FIX_CREATED,
                    notes=f"Fix draft saved to {draft_path}"
                )
                self.memory.record_fix_attempt(
                    issue_id,
                    status="fix_draft_created",
                    approach="Claude-generated fix draft (not applied)",
                    changes_made=str(draft_path)
                )
                console.print("\n[bold green]Fix draft generated for manual review.[/bold green]")
                console.print(f"[green]Draft: {draft_path}[/green]")
                return True

            if not self._ensure_clean_worktree():
                raise Exception("Worktree is not clean; refusing to apply edits")

            # Step 5: Apply → Build → Revise loop
            build_ok = False
            applied_originals: Dict[Path, str] = {}
            for attempt in range(1, max_build_attempts + 1):
                console.print(f"\n[bold cyan]Build attempt {attempt}/{max_build_attempts}[/bold cyan]")

                # 5a. Apply edits
                apply_ok, apply_errors, originals = self.apply_edits(edits)
                if not apply_ok:
                    errors.extend(apply_errors)
                    if attempt < max_build_attempts:
                        revised = self.revise_fix(
                            issue, edits,
                            "Apply failed:\n" + "\n".join(apply_errors),
                            workspace_context=workspace_context,
                        )
                        if revised and revised.get('edits'):
                            edits = revised['edits']
                            summary = revised.get('summary', summary)
                            continue
                    break

                applied_originals = originals

                # 5b. Build
                if build_dir and self.build_fixes:
                    build_ok, build_output = self.build_project(build_dir)
                elif build_dir:
                    console.print("[yellow]Build disabled by MEMFAULT_AI_BUILD_FIXES=false — skipping build verification[/yellow]")
                    build_ok = True
                    build_output = ""
                    break
                else:
                    console.print("[yellow]No build_dir — skipping build verification[/yellow]")
                    build_ok = True
                    build_output = ""
                    break

                if build_ok:
                    break  # success

                # 5c. Build failed — revert and revise
                console.print(f"[yellow]Reverting changes for retry...[/yellow]")
                self.restore_originals(applied_originals)

                if attempt < max_build_attempts:
                    revised = self.revise_fix(
                        issue, edits, build_output,
                        workspace_context=workspace_context,
                    )
                    if revised and revised.get('edits'):
                        edits = revised['edits']
                        summary = revised.get('summary', summary)
                    else:
                        console.print("[red]Claude could not produce a revised fix[/red]")
                        break

            if not build_ok:
                raise Exception(
                    f"Build failed after {max_build_attempts} attempts"
                )

            # Step 6: Commit
            self.memory.update_fix_status(issue_id, FixStatus.FIX_CREATED)
            commit_sha = None
            if self.commit_fixes:
                commit_sha = self.commit_changes(issue_id, summary, list(applied_originals.keys()))
            else:
                console.print("[yellow]Skipping commit; set MEMFAULT_AI_COMMIT_FIXES=true to enable commits.[/yellow]")

            # Step 7: Save to analysis file + update memory
            raw_content = json.dumps({
                "summary": summary,
                "edits": edits,
            }, indent=2)

            status_msg = "fix_committed" if commit_sha else "fix_applied_uncommitted"
            self.memory.record_fix_attempt(
                issue_id,
                status=status_msg,
                approach="Claude-generated fix (explicitly applied)",
                changes_made=raw_content[:1000]
            )

            console.print(f"\n[bold green]Fix applied successfully.[/bold green]")
            if commit_sha:
                console.print(f"[green]Commit: {commit_sha[:8]}[/green]")
            else:
                console.print("[yellow]Changes are uncommitted and require manual review.[/yellow]")
            return True

        except Exception as e:
            console.print(f"[red]Fix attempt failed: {e}[/red]")
            self.memory.update_fix_status(issue_id, FixStatus.FAILED, notes=str(e))
            self.memory.record_fix_attempt(
                issue_id,
                status="failed",
                error_message=str(e)
            )
            return False

        finally:
            self.close_workspace_shell()

"""Claude-powered analysis of Memfault issues."""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from anthropic import Anthropic
from config import Config


class ClaudeAnalyzer:
    """Analyzer that uses Claude to provide root cause analysis."""

    def __init__(
        self,
        api_key: str,
        source_code_path: Optional[Path] = None,
        model: Optional[str] = None,
        ai_client: Optional[str] = None,
    ):
        self.ai_client = ai_client or Config.AI_CLIENT
        if self.ai_client != "anthropic":
            raise ValueError(f"Unsupported AI_CLIENT: {self.ai_client}")
        self.client = Anthropic(api_key=api_key)
        self.model = model or Config.AI_MODEL
        self.source_code_path = source_code_path

    def analyze_issue(self, issue: Dict, traces: List[Dict]) -> Dict[str, str]:
        """
        Analyze a Memfault issue using Claude.

        Args:
            issue: Issue data from Memfault
            traces: Sample traces for this issue

        Returns:
            Dictionary with analysis results including root_cause, fix_suggestions, etc.
        """
        issue_context = self._format_issue_context(issue, traces)

        # Add codebase documentation if available
        codebase_docs = self._get_codebase_documentation()
        if codebase_docs:
            issue_context = f"{codebase_docs}\n\n{issue_context}"

        # Add source code context if available (pass traces for stack trace analysis)
        source_context = self._get_source_code_context(issue, traces)
        if source_context:
            issue_context += f"\n\n{source_context}"

        prompt = f"""You are an expert firmware engineer analyzing a critical embedded systems issue from Memfault.

Your goal is to provide a detailed, actionable analysis that enables the team to fix this issue completely.

{issue_context}

# Analysis Requirements

Provide a comprehensive analysis with the following sections:

## 1. Root Cause Analysis
- Identify the exact cause of the failure (not just symptoms)
- Consider timing issues, race conditions, memory corruption, hardware dependencies
- If source code is provided, reference specific lines and functions
- Consider firmware lifecycle: initialization, runtime, shutdown, power states
- Analyze the error message and reason field carefully

## 2. Detailed Fix Recommendations
- Provide specific code changes with line numbers if source is available
- Include before/after code snippets
- Consider edge cases and failure modes
- Address both immediate fix and preventive measures
- If multiple approaches exist, explain trade-offs

## 3. Impact Assessment
- **Severity**: Critical/High/Medium/Low with justification
- **Scope**: Number of affected devices and software versions
- **User Impact**: What functionality is broken?
- **Urgency**: Should this be hotfixed or can it wait for next release?

## 4. Technical Details
- **Affected Components**: List all subsystems involved
- **Dependencies**: What other code or hardware is involved?
- **Concurrency Concerns**: Thread safety, ISR context, timing issues
- **Memory Implications**: Stack, heap, static allocation concerns
- **Hardware Interaction**: Peripheral registers, DMA, interrupts

## 5. Validation Strategy
- **Unit Tests**: What tests should be added?
- **Integration Tests**: How to test the complete flow?
- **Stress Testing**: How to reproduce and verify the fix?
- **Regression Prevention**: What checks prevent recurrence?
- **Monitoring**: What metrics should be tracked post-fix?

## 6. Additional Considerations
- Are there similar patterns elsewhere in the codebase?
- Could this indicate a systemic issue?
- Should coding standards or review processes be updated?

Be specific, technical, and actionable. Reference actual code, line numbers, and function names when available."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,  # Increased for detailed analysis
                temperature=0.2,  # Lower temperature for more focused, technical analysis
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            analysis_text = response.content[0].text

            return {
                "analysis": analysis_text,
                "model_used": self.model,
                "issue_id": issue.get("id", "unknown")
            }

        except Exception as e:
            return {
                "analysis": f"Error during analysis: {str(e)}",
                "model_used": self.model,
                "issue_id": issue.get("id", "unknown"),
                "error": str(e)
            }

    def _format_issue_context(self, issue: Dict, traces: List[Dict]) -> str:
        """Format issue and trace data for Claude analysis."""
        context_parts = []

        context_parts.append("## Issue Metadata")
        context_parts.append(f"- **Issue ID**: {issue.get('id', 'N/A')}")
        context_parts.append(f"- **Title**: {issue.get('title', 'N/A')}")
        context_parts.append(f"- **Status**: {issue.get('status', 'N/A')}")
        context_parts.append(f"- **First Seen**: {issue.get('first_seen', 'N/A')}")
        context_parts.append(f"- **Last Seen**: {issue.get('last_seen', 'N/A')}")
        context_parts.append(f"- **Total Occurrences**: {issue.get('trace_count', 'N/A')}")
        context_parts.append(f"- **Affected Devices**: {issue.get('device_count', 'N/A')}")

        if issue.get('first_software_version'):
            context_parts.append(f"- **First Software Version**: {issue['first_software_version']}")
        if issue.get('last_software_version'):
            context_parts.append(f"- **Last Software Version**: {issue['last_software_version']}")
        if issue.get('is_missing_symbol_files'):
            context_parts.append(f"- **Missing Symbol Files**: Yes (stack trace may be incomplete)")

        if issue.get('reason'):
            context_parts.append(f"\n## Error Reason\n{issue['reason']}")

        if issue.get('message'):
            context_parts.append(f"\n## Error Message\n{issue['message']}")

        if issue.get('description'):
            context_parts.append(f"\n## Description\n{issue['description']}")

        if issue.get('error_type'):
            context_parts.append(f"\n## Error Type\n{issue['error_type']}")

        if issue.get('stack_trace'):
            context_parts.append(f"\n## Stack Trace\n```\n{issue['stack_trace']}\n```")

        if issue.get('software_type'):
            context_parts.append(f"\n## Software Type\n{issue['software_type']}")

        if issue.get('software_version'):
            context_parts.append(f"**Version**: {issue['software_version']}")

        if issue.get('hardware_version'):
            context_parts.append(f"**Hardware**: {issue['hardware_version']}")

        # Include any other relevant debugging fields
        relevant_fields = ['coredump_available', 'exception_info', 'registers', 'thread_info']
        for field in relevant_fields:
            if issue.get(field):
                context_parts.append(f"\n## {field.replace('_', ' ').title()}\n```json\n{json.dumps(issue[field], indent=2)}\n```")

        # Detailed traces with threads and stack traces
        if traces:
            context_parts.append(f"\n## Detailed Trace Analysis ({len(traces)} traces)")
            for idx, trace in enumerate(traces[:2], 1):  # Analyze up to 2 traces in detail
                context_parts.append(f"\n### Trace {idx}")

                device = trace.get('device', {})
                device_serial = device.get('device_serial', 'N/A') if isinstance(device, dict) else 'N/A'

                context_parts.append(f"- **Captured**: {trace.get('captured_date', 'N/A')}")
                context_parts.append(f"- **Device**: {device_serial}")
                context_parts.append(f"- **Reason**: {trace.get('reason', 'N/A')}")
                context_parts.append(f"- **Title**: {trace.get('title', 'N/A')}")

                # Thread information (CRITICAL for firmware debugging)
                entries = trace.get('entries', {})
                if isinstance(entries, dict):
                    # Logs (often contains error messages)
                    if 'logs' in entries:
                        logs = entries['logs']
                        context_parts.append(f"\n#### Logs")
                        for log_source, log_data in logs.items():
                            if 'lines' in log_data:
                                context_parts.append(f"**{log_source}**:")
                                for log_entry in log_data['lines'][:10]:  # Show up to 10 log lines
                                    line_text = log_entry.get('line', '')
                                    if line_text:
                                        context_parts.append(f"  {line_text}")

                    # Fault information
                    if 'faults' in entries:
                        faults = entries['faults']
                        context_parts.append(f"\n#### Fault Information")
                        if 'notes' in faults:
                            context_parts.append("**Notes**:")
                            for note in faults['notes']:
                                context_parts.append(f"  - {note}")

                        if 'registers' in faults and faults['registers']:
                            context_parts.append("\n**Fault Registers**:")
                            for reg in faults['registers'][:5]:  # Show key registers
                                context_parts.append(f"  - {reg['name']}: 0x{reg['data']} ({reg.get('value', 'N/A')})")

                    # Thread information
                    if 'threads' in entries:
                        threads = entries['threads']
                        context_parts.append(f"\n#### Threads ({len(threads)} threads)")

                        for thread in threads:
                            tid = thread.get('tid', 'N/A')
                            name = thread.get('name', 'Unknown')
                            state = thread.get('state', 'unknown')
                            crashed = thread.get('crashed', False)
                            current = thread.get('current', False)

                            markers = []
                            if crashed:
                                markers.append("**CRASHED**")
                            if current:
                                markers.append("**CURRENT**")

                            context_parts.append(f"\n**Thread {tid}: {name}**")
                            context_parts.append(f"  - State: {state}")
                            if markers:
                                context_parts.append(f"  - Status: {', '.join(markers)}")

                            # Include registers for crashed/current thread
                            if (crashed or current) and 'registers' in thread:
                                registers = thread['registers']
                                context_parts.append(f"  - Key Registers:")
                                # Show PC, LR, SP at minimum
                                key_regs = ['pc', 'lr', 'sp', 'r0', 'r1', 'r2', 'r3']
                                for reg in registers:
                                    if reg['name'].lower() in key_regs:
                                        context_parts.append(f"      {reg['name']}: 0x{reg['data']} = {reg.get('value', 'N/A')}")

                            # Include stack trace
                            if 'stacktrace' in thread:
                                stacktrace = thread['stacktrace']
                                context_parts.append(f"  - Stack Trace ({len(stacktrace)} frames):")

                                for frame in stacktrace[:15]:  # Show up to 15 frames for Claude
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

                                    # Format for Claude
                                    if file_name and line:
                                        context_parts.append(f"      {func_name} at {file_name}:{line}")
                                    elif file_name:
                                        context_parts.append(f"      {func_name} in {file_name}")
                                    elif addr:
                                        context_parts.append(f"      {addr}: {func_name}")
                                    else:
                                        context_parts.append(f"      {func_name}")

        return "\n".join(context_parts)

    def _get_source_code_context(self, issue: Dict, traces: List[Dict] = None) -> Optional[str]:
        """
        Extract relevant source code files based on the issue.

        Args:
            issue: Issue data from Memfault
            traces: Trace data with stack traces

        Returns:
            Formatted source code context or None
        """
        if not self.source_code_path or not self.source_code_path.exists():
            return None

        context_parts = []
        context_parts.append("## Relevant Source Code")

        # Extract function/file names from title, message, and stack traces
        relevant_files = self._find_relevant_files(issue, traces)

        if not relevant_files:
            context_parts.append("\n*No specific source files identified from error message*")
            return "\n".join(context_parts)

        # Read and include relevant source files
        files_added = 0
        for file_path in relevant_files[:5]:  # Limit to 5 most relevant files (increased for stack traces)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.split('\n')

                    # Limit file size to avoid token overflow
                    if len(content) > 8000:
                        content = content[:8000] + "\n... (truncated)"

                    relative_path = file_path.relative_to(self.source_code_path)
                    context_parts.append(f"\n### File: `{relative_path}` ({len(lines)} lines)")

                    # Detect language from extension
                    ext = file_path.suffix.lower()
                    lang = 'c' if ext in ['.c', '.h'] else 'cpp' if ext in ['.cpp', '.hpp'] else 'text'

                    context_parts.append(f"```{lang}\n{content}\n```")
                    files_added += 1
            except Exception as e:
                context_parts.append(f"\n*Could not read {file_path}: {e}*")

        if files_added > 0:
            return "\n".join(context_parts)
        return None

    def _find_relevant_files(self, issue: Dict, traces: List[Dict] = None) -> List[Path]:
        """
        Find source files relevant to the issue.

        Args:
            issue: Issue data from Memfault
            traces: Trace data with stack traces

        Returns:
            List of relevant file paths
        """
        if not self.source_code_path:
            return []

        relevant_files = []

        # First priority: Extract files from stack traces
        if traces:
            for trace in traces[:2]:  # Check first 2 traces
                entries = trace.get('entries', {})
                if isinstance(entries, dict) and 'threads' in entries:
                    for thread in entries['threads']:
                        if 'stacktrace' in thread:
                            for frame in thread['stacktrace'][:10]:  # Top 10 frames
                                # Extract file path from frame
                                file_name = frame.get('file', '')

                                if file_name:
                                    # Replace WEST_TOPDIR with SOURCE_CODE_PATH
                                    if 'WEST_TOPDIR' in file_name:
                                        file_name = file_name.replace('WEST_TOPDIR/', '')

                                    # Try to find this exact file
                                    file_path = self.source_code_path / file_name
                                    if file_path.exists():
                                        relevant_files.append(file_path)
                                    else:
                                        # Try finding by basename
                                        basename = Path(file_name).name
                                        try:
                                            matches = list(self.source_code_path.glob(f"**/{basename}"))
                                            if matches:
                                                relevant_files.extend(matches[:1])
                                        except Exception:
                                            continue

        # Second priority: Extract from title and message (fallback)
        if not relevant_files:
            title = issue.get('title', '')
            message = issue.get('message', '')

            search_terms = []

            # Extract words from title (after "Error at" or "Assert at")
            match = re.search(r'(?:Error|Assert) at (\w+)', title)
            if match:
                search_terms.append(match.group(1))

            # Extract function names from message
            func_matches = re.findall(r'\b([a-z_][a-z0-9_]{3,})\b', message.lower())
            search_terms.extend(func_matches[:3])

            # Search for files containing these terms
            for term in search_terms:
                if term:
                    for pattern in [f"**/*{term}*.c", f"**/*{term}*.cpp", f"**/*{term}*.h"]:
                        try:
                            matches = list(self.source_code_path.glob(pattern))
                            relevant_files.extend(matches[:2])
                        except Exception:
                            continue

        # Remove duplicates while preserving order
        seen = set()
        unique_files = []
        for f in relevant_files:
            if f not in seen:
                seen.add(f)
                unique_files.append(f)

        return unique_files[:5]  # Return max 5 most relevant files (increased for stack traces)

    def _get_codebase_documentation(self) -> Optional[str]:
        """
        Load codebase documentation like AGENT.md, README.md, ARCHITECTURE.md.

        Returns:
            Formatted documentation context or None
        """
        if not self.source_code_path or not self.source_code_path.exists():
            return None

        doc_parts = []

        # Look for documentation files in order of preference
        doc_files = [
            'AGENT.md',
            'CLAUDE.md',
            'AI_CONTEXT.md',
            'ARCHITECTURE.md',
            'CONTRIBUTING.md',
            'README.md',
            'DEVELOPMENT.md',
            'docs/ARCHITECTURE.md',
            'docs/CONTRIBUTING.md',
        ]

        found_docs = []
        for doc_file in doc_files:
            doc_path = self.source_code_path / doc_file
            if doc_path.exists():
                try:
                    with open(doc_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                        # Limit size to avoid token overflow
                        if len(content) > 10000:
                            content = content[:10000] + "\n... (truncated)"

                        found_docs.append({
                            'name': doc_file,
                            'content': content
                        })

                        # Stop after finding 2 most relevant docs
                        if len(found_docs) >= 2:
                            break
                except Exception:
                    continue

        if not found_docs:
            return None

        doc_parts.append("# Codebase Context\n")
        doc_parts.append("The following documentation provides context about the codebase architecture and conventions:\n")

        for doc in found_docs:
            doc_parts.append(f"\n## From {doc['name']}:\n")
            doc_parts.append(doc['content'])

        return "\n".join(doc_parts)


def create_analyzer() -> ClaudeAnalyzer:
    """Create a configured Claude analyzer."""
    return ClaudeAnalyzer(
        api_key=Config.ANTHROPIC_API_KEY,
        source_code_path=Config.SOURCE_CODE_PATH,
        model=Config.AI_MODEL,
        ai_client=Config.AI_CLIENT,
    )

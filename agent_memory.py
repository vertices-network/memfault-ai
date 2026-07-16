"""Agent memory system for tracking issues, analyses, and fix attempts."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class FixStatus(Enum):
    """Status of a fix attempt."""
    NOT_STARTED = "not_started"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    FIX_IN_PROGRESS = "fix_in_progress"
    FIX_CREATED = "fix_created"
    TESTING = "testing"
    TEST_PASSED = "test_passed"
    TEST_FAILED = "test_failed"
    BRANCH_PUSHED = "branch_pushed"
    PR_CREATED = "pr_created"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class IssueRecord:
    """Record of a Memfault issue in agent memory."""
    issue_id: str
    title: str
    reason: str
    message: str
    trace_count: int
    device_count: int
    first_seen: str
    last_seen: str
    status: str
    software_versions: str
    analysis_date: Optional[str] = None
    analysis_file: Optional[str] = None
    fix_status: str = FixStatus.NOT_STARTED.value
    branch_name: Optional[str] = None
    commit_sha: Optional[str] = None
    fix_attempt_count: int = 0
    last_attempt_date: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AgentMemory:
    """Persistent storage for agent's memory of issues and fixes."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS issues (
                issue_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                reason TEXT,
                message TEXT,
                trace_count INTEGER,
                device_count INTEGER,
                first_seen TEXT,
                last_seen TEXT,
                status TEXT,
                software_versions TEXT,
                analysis_date TEXT,
                analysis_file TEXT,
                fix_status TEXT DEFAULT 'not_started',
                branch_name TEXT,
                commit_sha TEXT,
                fix_attempt_count INTEGER DEFAULT 0,
                last_attempt_date TEXT,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fix_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                approach TEXT,
                changes_made TEXT,
                test_results TEXT,
                error_message TEXT,
                FOREIGN KEY (issue_id) REFERENCES issues(issue_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    def store_issue(self, issue: Dict, analysis_file: Optional[Path] = None):
        """Store or update an issue in memory."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        software_versions = json.dumps({
            'first': issue.get('first_software_version'),
            'last': issue.get('last_software_version')
        })

        cursor.execute("""
            INSERT OR REPLACE INTO issues (
                issue_id, title, reason, message, trace_count, device_count,
                first_seen, last_seen, status, software_versions,
                analysis_date, analysis_file, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            str(issue.get('id')),
            issue.get('title', ''),
            issue.get('reason', ''),
            issue.get('message', ''),
            issue.get('trace_count', 0),
            issue.get('device_count', 0),
            issue.get('first_seen', ''),
            issue.get('last_seen', ''),
            issue.get('status', ''),
            software_versions,
            datetime.now().isoformat() if analysis_file else None,
            str(analysis_file) if analysis_file else None
        ))

        conn.commit()
        conn.close()

    def get_issue(self, issue_id: str) -> Optional[IssueRecord]:
        """Retrieve an issue from memory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM issues WHERE issue_id = ?", (issue_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return IssueRecord(**dict(row))
        return None

    def get_all_issues(self) -> List[IssueRecord]:
        """Retrieve all issues from memory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM issues ORDER BY device_count DESC")
        rows = cursor.fetchall()
        conn.close()

        return [IssueRecord(**dict(row)) for row in rows]

    def get_issues_by_status(self, fix_status: FixStatus) -> List[IssueRecord]:
        """Get issues filtered by fix status."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM issues WHERE fix_status = ? ORDER BY device_count DESC",
            (fix_status.value,)
        )
        rows = cursor.fetchall()
        conn.close()

        return [IssueRecord(**dict(row)) for row in rows]

    def update_fix_status(self, issue_id: str, status: FixStatus, notes: Optional[str] = None):
        """Update the fix status of an issue."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE issues
            SET fix_status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE issue_id = ?
        """, (status.value, notes, issue_id))

        conn.commit()
        conn.close()

    def record_fix_attempt(
        self,
        issue_id: str,
        status: str,
        approach: Optional[str] = None,
        changes_made: Optional[str] = None,
        test_results: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """Record a fix attempt."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get current attempt count
        cursor.execute(
            "SELECT fix_attempt_count FROM issues WHERE issue_id = ?",
            (issue_id,)
        )
        row = cursor.fetchone()
        attempt_number = (row[0] if row else 0) + 1

        # Insert attempt record
        cursor.execute("""
            INSERT INTO fix_attempts (
                issue_id, attempt_number, started_at, completed_at,
                status, approach, changes_made, test_results, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            issue_id,
            attempt_number,
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            status,
            approach,
            changes_made,
            test_results,
            error_message
        ))

        # Update issue record
        cursor.execute("""
            UPDATE issues
            SET fix_attempt_count = ?,
                last_attempt_date = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE issue_id = ?
        """, (attempt_number, issue_id))

        conn.commit()
        conn.close()

    def update_branch_info(self, issue_id: str, branch_name: str, commit_sha: Optional[str] = None):
        """Update branch and commit information for an issue."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE issues
            SET branch_name = ?, commit_sha = ?, updated_at = CURRENT_TIMESTAMP
            WHERE issue_id = ?
        """, (branch_name, commit_sha, issue_id))

        conn.commit()
        conn.close()

    def get_statistics(self) -> Dict:
        """Get statistics about the agent's work."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        stats = {}

        # Total issues
        cursor.execute("SELECT COUNT(*) FROM issues")
        stats['total_issues'] = cursor.fetchone()[0]

        # Status breakdown
        cursor.execute("SELECT fix_status, COUNT(*) FROM issues GROUP BY fix_status")
        stats['by_status'] = dict(cursor.fetchall())

        # Total attempts
        cursor.execute("SELECT COUNT(*) FROM fix_attempts")
        stats['total_attempts'] = cursor.fetchone()[0]

        # Success rate
        cursor.execute("""
            SELECT COUNT(*) FROM issues
            WHERE fix_status IN ('test_passed', 'branch_pushed', 'completed')
        """)
        stats['successful_fixes'] = cursor.fetchone()[0]

        conn.close()
        return stats

    def set_agent_state(self, key: str, value: str):
        """Store agent state."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO agent_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (key, value))

        conn.commit()
        conn.close()

    def get_agent_state(self, key: str) -> Optional[str]:
        """Retrieve agent state."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT value FROM agent_state WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()

        return row[0] if row else None

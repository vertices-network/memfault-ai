"""Client for interacting with Memfault API."""
import requests
from typing import List, Dict, Optional
from config import Config


class MemfaultClient:
    """Client for Memfault API operations."""

    def __init__(self, api_key: str, org_slug: str, project_slug: str, base_url: str):
        self.api_key = api_key
        self.org_slug = org_slug
        self.project_slug = project_slug
        self.base_url = base_url
        self.session = requests.Session()
        # Memfault uses HTTP Basic Auth with empty username and token as password
        self.session.auth = ('', api_key)
        self.session.headers.update({
            "Content-Type": "application/json"
        })

    def get_issues(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """
        Fetch issues from Memfault.

        Args:
            status: Filter by status (unresolved, resolved, muted, merged)
            limit: Maximum number of issues to return
            offset: Pagination offset

        Returns:
            List of issue dictionaries
        """
        url = f"{self.base_url}/api/v0/organizations/{self.org_slug}/projects/{self.project_slug}/issues"

        params = {
            "limit": limit,
            "offset": offset
        }

        if status:
            params["status"] = status

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # Handle different response structures
            if isinstance(data, dict):
                issues = data.get("data", data.get("results", []))
                return issues
            elif isinstance(data, list):
                return data
            else:
                print(f"Unexpected response type: {type(data)}")
                return []
        except requests.exceptions.RequestException as e:
            print(f"Error fetching issues: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response status: {e.response.status_code}")
                print(f"Response body: {e.response.text}")
            return []
        except Exception as e:
            print(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return []

    def filter_issues_by_version(
        self,
        issues: List[Dict],
        version_filter: str,
        filter_mode: str = "only"
    ) -> List[Dict]:
        """
        Filter issues by software version.

        Args:
            issues: List of issues to filter
            version_filter: Version string to filter by (e.g., "3.1.19")
            filter_mode: "only" = only in this version,
                        "started" = first appeared in this version,
                        "present" = present in this version

        Returns:
            Filtered list of issues
        """
        filtered = []

        for issue in issues:
            first_ver = issue.get('first_software_version', {})
            last_ver = issue.get('last_software_version', {})

            if not isinstance(first_ver, dict) or not isinstance(last_ver, dict):
                continue

            first_ver_str = first_ver.get('version', '')
            last_ver_str = last_ver.get('version', '')

            if filter_mode == "only":
                # Issue only occurs in this specific version
                if first_ver_str == version_filter and last_ver_str == version_filter:
                    filtered.append(issue)

            elif filter_mode == "started":
                # Issue first appeared in this version
                if first_ver_str == version_filter:
                    filtered.append(issue)

            elif filter_mode == "present":
                # Issue is present in this version (between first and last)
                # Simple string comparison - works if versions are sequential
                if first_ver_str <= version_filter <= last_ver_str:
                    filtered.append(issue)

            elif filter_mode == "exclude":
                # Exclude issues in this version
                if not (first_ver_str <= version_filter <= last_ver_str):
                    filtered.append(issue)

        return filtered

    def get_issue_details(self, issue_id: str) -> Optional[Dict]:
        """
        Fetch detailed information about a specific issue.

        Args:
            issue_id: The issue ID to fetch

        Returns:
            Issue details dictionary or None if error
        """
        url = f"{self.base_url}/api/v0/organizations/{self.org_slug}/projects/{self.project_slug}/issues/{issue_id}"

        try:
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()

            # Handle nested response structure
            if isinstance(data, dict) and 'data' in data:
                return data['data']
            return data
        except requests.exceptions.RequestException as e:
            print(f"Error fetching issue details: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response status: {e.response.status_code}")
                print(f"Response body: {e.response.text}")
            return None

    def get_issue_traces(self, issue_id: str, limit: int = 5) -> List[Dict]:
        """
        Fetch detailed traces for a specific issue.

        Uses the /issues/{id}/first-trace endpoint which correctly returns
        traces belonging to the specified issue.

        Args:
            issue_id: The issue ID
            limit: Maximum number of traces to return

        Returns:
            List of detailed trace dictionaries with threads and stack traces
        """
        traces = []

        try:
            # Use the first-trace endpoint to get the most recent trace
            first_trace_url = f"{self.base_url}/api/v0/organizations/{self.org_slug}/projects/{self.project_slug}/issues/{issue_id}/first-trace"

            response = self.session.get(first_trace_url, params={"sort": "-created_date"})

            if response.status_code == 200:
                data = response.json()
                if "data" in data:
                    trace = data["data"]
                    # Verify it belongs to our issue
                    if str(trace.get("issue_id")) == str(issue_id):
                        traces.append(trace)

            # If we need more traces, we could try pagination or other endpoints
            # For now, return the first trace which has the most recent data
            return traces

        except requests.exceptions.RequestException as e:
            print(f"Error fetching traces: {e}")
            return []


def create_client() -> MemfaultClient:
    """Create a configured Memfault client."""
    return MemfaultClient(
        api_key=Config.MEMFAULT_API_KEY,
        org_slug=Config.MEMFAULT_ORG_SLUG,
        project_slug=Config.MEMFAULT_PROJECT_SLUG,
        base_url=Config.MEMFAULT_API_BASE_URL
    )

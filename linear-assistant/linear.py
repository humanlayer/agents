from typing import Dict, Optional, Any
import requests


class LinearClient:
    """Client for interacting with the Linear API."""

    BASE_URL = "https://api.linear.app/graphql"

    def __init__(self, api_key: str):
        """Initialize the Linear client with an API key.

        Args:
            api_key: Linear API key for authentication
        """
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        )

    def _make_request(
        self, query: str, variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a GraphQL request to the Linear API.

        Args:
            query: GraphQL query string
            variables: Optional variables for the GraphQL query

        Returns:
            Dict containing the response data

        Raises:
            requests.exceptions.RequestException: If the request fails
        """
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        response = self.session.post(self.BASE_URL, json=payload)
        response.raise_for_status()
        return response.json()

    def get_all_issues_assigned_to_user(self, email: str) -> Dict[str, Any]:
        """Get all issues assigned to a user by email."""
        query = """
        query GetUserIssues($email: String!) {
            users(filter: { email: { eq: $email } }) {
                nodes {
                    id
                    name
                    assignedIssues {
                        nodes {
                            id
                            title
                            description
                            url
                        }
                    }
                }
            }
        }
        """
        return self._make_request(query, variables={"email": email})

    def get_issue_details(self, issue_id: str) -> Dict[str, Any]:
        """Get detailed information about a specific issue."""
        query = """
        query GetIssueDetails($issueId: String!) {
            issue(id: $issueId) {
                id
                title
                description
                assignee {
                    name
                }
                state {
                    name
                }
            }
        }
        """
        return self._make_request(query, variables={"issueId": issue_id})

    def list_all_teams(self) -> Dict[str, Any]:
        """List all teams and their members."""
        query = """
        query {
            teams {
                nodes {
                    id
                    name
                    members {
                        nodes {
                            email
                            id
                            displayName
                        }
                    }
                }
            }
        }
        """
        return self._make_request(query)

    def get_default_team_id(self) -> str:
        """Get the ID of the most recently created team."""
        query = """
        query {
            teams(orderBy: { createdAt: DESC }, first: 1) {
                nodes {
                    id
                    name
                    createdAt
                }
            }
        }
        """
        response = self._make_request(query)
        return response["data"]["teams"]["nodes"][0]["id"]

    def list_all_issues(self, from_time: str, to_time: str) -> Dict[str, Any]:
        """List all issues created within a time window."""
        query = """
        query AllIssuesInTimeWindow($from_time: DateTime!, $to_time: DateTime!) {
            issues(
                filter: { createdAt: { gte: $from_time, lte: $to_time } }
                orderBy: { createdAt: ASC }
            ) {
                nodes {
                    id
                    title
                    description
                    url
                    createdAt
                    assignee { name }
                }
            }
        }
        """
        return self._make_request(
            query, variables={"from_time": from_time, "to_time": to_time}
        )

    def create_issue(
        self, title: str, description: str, team_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new issue with the given title and description."""
        if not team_id:
            team_id = self.get_default_team_id()

        query = """
        mutation CreateIssue($title: String!, $description: String!, $teamId: String!) {
            issueCreate(
                input: {
                    title: $title,
                    description: $description,
                    teamId: $teamId
                }
            ) {
                success
                issue {
                    id
                    title
                    description
                }
            }
        }
        """
        return self._make_request(
            query,
            variables={"title": title, "description": description, "teamId": team_id},
        )

    def assign_issue(self, issue_id: str, email: str) -> Dict[str, Any]:
        """Assign an issue to a user by email."""
        user_response = self._make_request(
            """
            query GetUserByEmail($email: String!) {
                users(filter: { email: { eq: $email } }) {
                    nodes {
                        id
                    }
                }
            }
        """,
            variables={"email": email},
        )

        user_id = user_response["data"]["users"]["nodes"][0]["id"]

        query = """
        mutation AssignIssue($issueId: String!, $userId: String!) {
            issueUpdate(
                id: $issueId,
                input: { assigneeId: $userId }
            ) {
                issue {
                    id
                    title
                    assignee {
                        id
                        name
                    }
                }
            }
        }
        """
        return self._make_request(
            query, variables={"issueId": issue_id, "userId": user_id}
        )

    def get_high_priority_issues(self) -> Dict[str, Any]:
        """Find all urgent and high priority issues (priority <= 2)."""
        query = """
        query {
            issues(filter: { priority: { lte: 2 } }) {
                nodes {
                    id
                    title
                    priority
                }
            }
        }
        """
        return self._make_request(query)

    def get_unassigned_issues(self) -> Dict[str, Any]:
        """Find all issues without an assignee."""
        query = """
        query {
            issues(filter: { assignee: { null: true } }) {
                nodes {
                    id
                    title
                    description
                    url
                }
            }
        }
        """
        return self._make_request(query)

    def get_issues_by_label(self, label: str) -> Dict[str, Any]:
        """Find issues with a specific label."""
        query = """
        query IssuesWithLabel($label: String!) {
            issues(filter: { labels: { name: { eq: $label } } }) {
                nodes {
                    id
                    title
                }
            }
        }
        """
        return self._make_request(query, variables={"label": label})

    def get_issues_due_by(self, due_date: str) -> Dict[str, Any]:
        """Find issues due before a specific date."""
        query = """
        query IssuesDue($dueDate: TimelessDate!) {
            issues(filter: { dueDate: { lt: $dueDate } }) {
                nodes {
                    id
                    title
                }
            }
        }
        """
        return self._make_request(query, variables={"dueDate": due_date})


# client = LinearClient(api_key="linear_key")
#
# # Get all teams
# teams = client.list_all_teams()
#
# # Create an issue
# issue = client.create_issue(title="New bug", description="Found a critical issue")
#
# # Assign an issue
# client.assign_issue(issue_id="issue_id", email="user@example.com")

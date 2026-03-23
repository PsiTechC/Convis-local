"""
Jira Integration Service
Handles Jira API operations for creating and updating tickets
"""
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime
from urllib.parse import urlparse
import logging
import re
from app.models.integration import JiraCredentials
from app.services.integrations.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class JiraService:
    """Jira API integration service"""

    @staticmethod
    def normalize_jira_url(url: str) -> str:
        """
        Normalize Jira URL to extract just the base Atlassian domain.

        Handles various input formats:
        - https://company.atlassian.net/jira/software/projects/ABC
        - company.atlassian.net
        - https://company.atlassian.net/
        - http://company.atlassian.net

        Returns the normalized URL: https://company.atlassian.net
        """
        if not url:
            return url

        url = url.strip()

        # Add https:// if no scheme provided
        if not url.startswith('http://') and not url.startswith('https://'):
            url = 'https://' + url

        try:
            parsed = urlparse(url)
            hostname = parsed.netloc or parsed.path.split('/')[0]

            # Clean up hostname (remove any path components that got mixed in)
            hostname = hostname.split('/')[0]

            # Validate it looks like an Atlassian domain
            if hostname and '.atlassian.net' in hostname:
                return f"https://{hostname}"
            elif hostname:
                # Might be a self-hosted Jira, return with https
                return f"https://{hostname}"
            else:
                return url
        except Exception as e:
            logger.warning(f"Failed to parse Jira URL '{url}': {e}")
            return url

    def __init__(self, credentials: JiraCredentials):
        """Initialize Jira service with credentials"""
        # Normalize the URL to extract just the base domain
        raw_url = credentials.base_url.rstrip('/')
        self.base_url = self.normalize_jira_url(raw_url)

        logger.info(f"Jira service initialized with base URL: {self.base_url} (original: {raw_url})")

        self.email = credentials.email
        self.api_token = credentials.api_token
        self.default_project = credentials.default_project
        self.default_issue_type = credentials.default_issue_type or "Task"

        # Setup authentication
        self.auth = (self.email, self.api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to Jira API"""
        url = f"{self.base_url}/rest/api/3/{endpoint.lstrip('/')}"

        try:
            response = requests.request(
                method=method,
                url=url,
                json=data,
                params=params,
                auth=self.auth,
                headers=self.headers,
                timeout=30
            )

            response.raise_for_status()
            return response.json() if response.text else {}

        except requests.exceptions.HTTPError as e:
            logger.error(f"Jira API HTTP error: {e}")
            logger.error(f"Response: {e.response.text if e.response else 'No response'}")
            raise Exception(f"Jira API error: {e.response.text if e.response else str(e)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Jira API request error: {e}")
            raise Exception(f"Jira connection error: {str(e)}")

    def test_connection(self) -> Dict[str, Any]:
        """Test Jira connection and credentials"""
        try:
            # Log connection attempt details (without exposing full token)
            token_preview = self.api_token[:4] + "..." + self.api_token[-4:] if len(self.api_token) > 8 else "***"
            logger.info(f"Testing Jira connection to {self.base_url} with email {self.email}, token preview: {token_preview}")

            # Try to get current user info
            result = self._make_request("GET", "/myself")
            return {
                "success": True,
                "message": "Successfully connected to Jira",
                "user": result.get("displayName", result.get("emailAddress", "Unknown"))
            }
        except Exception as e:
            error_message = str(e)
            logger.error(f"Jira connection test failed for {self.email} at {self.base_url}: {error_message}")

            # Provide helpful troubleshooting messages based on error type
            troubleshooting = []

            if "Host validation failed" in error_message or "Host is not supported" in error_message:
                troubleshooting = [
                    "This error typically occurs due to Jira API restrictions.",
                    "Solutions:",
                    "1. Verify your API token has proper permissions at https://id.atlassian.com/manage-profile/security/api-tokens",
                    "2. Ensure your Jira workspace allows API access",
                    "3. Check that the email matches your Jira account",
                    "4. Try regenerating a new API token",
                    "5. Contact your Jira admin to verify API access is enabled"
                ]
            elif "401" in error_message or "Unauthorized" in error_message:
                troubleshooting = [
                    "Authentication failed (401 Unauthorized). Please check:",
                    f"1. The email '{self.email}' is your Atlassian login email",
                    "2. Generate a NEW API token at: https://id.atlassian.com/manage-profile/security/api-tokens",
                    "3. Copy the token immediately (shown only once)",
                    "4. Make sure there are no spaces before/after the token when pasting",
                    "5. Your Atlassian account has access to this Jira workspace"
                ]
            elif "403" in error_message or "Forbidden" in error_message:
                troubleshooting = [
                    "Access forbidden. Please ensure:",
                    "1. Your API token has the required permissions",
                    "2. Your account has access to the Jira workspace",
                    "3. API access is not restricted by your organization"
                ]
            elif "404" in error_message or "Not Found" in error_message:
                troubleshooting = [
                    "Jira instance not found. Please verify:",
                    "1. The Jira domain URL is correct (e.g., yourcompany.atlassian.net)",
                    "2. The workspace exists and is accessible",
                    "3. You're using the correct Jira Cloud URL"
                ]
            elif "Expecting value" in error_message or "JSONDecodeError" in error_message:
                troubleshooting = [
                    "Invalid response from Jira server. This usually means:",
                    "1. The Jira URL format is incorrect",
                    "2. Use just the domain: yourcompany.atlassian.net",
                    "3. Do NOT include paths like /jira/software/projects/...",
                    "4. Make sure the Atlassian site exists and is accessible"
                ]
            else:
                troubleshooting = [
                    "Connection failed. Please verify:",
                    "1. Your Jira domain URL is correct (e.g., yourcompany.atlassian.net)",
                    "2. Your API token and email are valid",
                    "3. Your network allows connections to Jira"
                ]

            return {
                "success": False,
                "message": error_message,
                "troubleshooting": troubleshooting
            }

    def get_projects(self) -> List[Dict[str, Any]]:
        """Get list of accessible Jira projects"""
        try:
            projects = self._make_request("GET", "/project")
            return [
                {
                    "key": p.get("key"),
                    "name": p.get("name"),
                    "id": p.get("id")
                }
                for p in projects
            ]
        except Exception as e:
            logger.error(f"Error fetching Jira projects: {e}")
            return []

    def get_issue_types(self, project_key: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get available issue types for a project"""
        try:
            if project_key:
                # Get issue types for specific project
                project = self._make_request("GET", f"/project/{project_key}")
                issue_types = project.get("issueTypes", [])
            else:
                # Get all issue types
                issue_types = self._make_request("GET", "/issuetype")

            return [
                {
                    "id": it.get("id"),
                    "name": it.get("name"),
                    "description": it.get("description")
                }
                for it in issue_types
            ]
        except Exception as e:
            logger.error(f"Error fetching issue types: {e}")
            return []

    def create_issue(
        self,
        config: Dict[str, Any],
        context_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a Jira issue

        Args:
            config: Action configuration with project, issue_type, summary, description, etc.
            context_data: Data for template rendering

        Returns:
            Created issue details
        """
        try:
            # Render templates
            project = TemplateRenderer.render(
                config.get("project", self.default_project),
                context_data
            )

            issue_type = TemplateRenderer.render(
                config.get("issue_type", self.default_issue_type),
                context_data
            )

            summary = TemplateRenderer.render(
                config.get("summary", "New Issue"),
                context_data
            )

            description = TemplateRenderer.render(
                config.get("description", ""),
                context_data
            )

            # Build issue data
            issue_data = {
                "fields": {
                    "project": {"key": project},
                    "summary": summary,
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": description
                                    }
                                ]
                            }
                        ]
                    },
                    "issuetype": {"name": issue_type}
                }
            }

            # Add optional fields
            if "priority" in config:
                priority = TemplateRenderer.render(config["priority"], context_data)
                issue_data["fields"]["priority"] = {"name": priority}

            if "assignee" in config:
                assignee = TemplateRenderer.render(config["assignee"], context_data)
                # Assignee can be email or account ID
                if "@" in assignee:
                    issue_data["fields"]["assignee"] = {"emailAddress": assignee}
                else:
                    issue_data["fields"]["assignee"] = {"id": assignee}

            if "labels" in config:
                labels = config["labels"]
                if isinstance(labels, str):
                    labels = [l.strip() for l in labels.split(",")]
                issue_data["fields"]["labels"] = [
                    TemplateRenderer.render(label, context_data) for label in labels
                ]

            if "components" in config:
                components = config["components"]
                if isinstance(components, str):
                    components = [c.strip() for c in components.split(",")]
                issue_data["fields"]["components"] = [
                    {"name": TemplateRenderer.render(comp, context_data)}
                    for comp in components
                ]

            # Custom fields
            if "custom_fields" in config:
                for field_id, value in config["custom_fields"].items():
                    rendered_value = TemplateRenderer.render(str(value), context_data)
                    issue_data["fields"][field_id] = rendered_value

            # Create the issue
            logger.info(f"Creating Jira issue in project {project}")
            result = self._make_request("POST", "/issue", data=issue_data)

            return {
                "success": True,
                "issue_key": result.get("key"),
                "issue_id": result.get("id"),
                "url": f"{self.base_url}/browse/{result.get('key')}",
                "message": f"Created Jira issue {result.get('key')}"
            }

        except Exception as e:
            logger.error(f"Error creating Jira issue: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to create Jira issue: {str(e)}"
            }

    def update_issue(
        self,
        issue_key: str,
        config: Dict[str, Any],
        context_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing Jira issue"""
        try:
            update_data = {"fields": {}}

            # Update allowed fields
            if "summary" in config:
                update_data["fields"]["summary"] = TemplateRenderer.render(
                    config["summary"], context_data
                )

            if "description" in config:
                description = TemplateRenderer.render(config["description"], context_data)
                update_data["fields"]["description"] = {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description}]
                        }
                    ]
                }

            if "status" in config:
                # Transition issue to new status
                status = TemplateRenderer.render(config["status"], context_data)
                transitions = self._make_request("GET", f"/issue/{issue_key}/transitions")

                # Find matching transition
                transition_id = None
                for t in transitions.get("transitions", []):
                    if t["name"].lower() == status.lower():
                        transition_id = t["id"]
                        break

                if transition_id:
                    self._make_request(
                        "POST",
                        f"/issue/{issue_key}/transitions",
                        data={"transition": {"id": transition_id}}
                    )

            # Update the issue
            if update_data["fields"]:
                self._make_request("PUT", f"/issue/{issue_key}", data=update_data)

            return {
                "success": True,
                "issue_key": issue_key,
                "url": f"{self.base_url}/browse/{issue_key}",
                "message": f"Updated Jira issue {issue_key}"
            }

        except Exception as e:
            logger.error(f"Error updating Jira issue: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to update Jira issue: {str(e)}"
            }

    def add_comment(
        self,
        issue_key: str,
        comment: str,
        context_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Add a comment to a Jira issue"""
        try:
            rendered_comment = TemplateRenderer.render(comment, context_data)

            comment_data = {
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": rendered_comment}]
                        }
                    ]
                }
            }

            result = self._make_request(
                "POST",
                f"/issue/{issue_key}/comment",
                data=comment_data
            )

            return {
                "success": True,
                "comment_id": result.get("id"),
                "message": f"Added comment to {issue_key}"
            }

        except Exception as e:
            logger.error(f"Error adding comment: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to add comment: {str(e)}"
            }

    def get_issue(self, issue_key: str) -> Dict[str, Any]:
        """Get issue details"""
        try:
            issue = self._make_request("GET", f"/issue/{issue_key}")
            return {
                "success": True,
                "issue": {
                    "key": issue.get("key"),
                    "summary": issue.get("fields", {}).get("summary"),
                    "status": issue.get("fields", {}).get("status", {}).get("name"),
                    "url": f"{self.base_url}/browse/{issue.get('key')}"
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

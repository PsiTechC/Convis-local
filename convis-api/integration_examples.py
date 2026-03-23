"""
Integration System - Example Usage Scripts
Run these examples to test the integration system
"""

import requests
import json

# Configuration
BASE_URL = "http://localhost:8000"
AUTH_TOKEN = "your-auth-token-here"  # Get this from login

headers = {
    "Authorization": f"Bearer {AUTH_TOKEN}",
    "Content-Type": "application/json"
}


def example_1_create_jira_integration():
    """Example 1: Create a Jira integration"""
    print("=== Creating Jira Integration ===")

    integration_data = {
        "name": "My Jira Integration",
        "type": "jira",
        "credentials": {
            "base_url": "https://yourcompany.atlassian.net",
            "email": "your-email@company.com",
            "api_token": "your-jira-api-token",
            "default_project": "SUPPORT",
            "default_issue_type": "Task"
        }
    }

    response = requests.post(
        f"{BASE_URL}/api/integrations",
        headers=headers,
        json=integration_data
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    return response.json().get("integration_id")


def example_2_create_email_integration():
    """Example 2: Create an Email integration"""
    print("\n=== Creating Email Integration ===")

    integration_data = {
        "name": "Gmail SMTP",
        "type": "email",
        "credentials": {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_username": "your-email@gmail.com",
            "smtp_password": "your-app-password",  # Use app password, not regular password
            "from_email": "your-email@gmail.com",
            "from_name": "Convis Support",
            "use_tls": True
        }
    }

    response = requests.post(
        f"{BASE_URL}/api/integrations",
        headers=headers,
        json=integration_data
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    return response.json().get("integration_id")


def example_3_create_hubspot_integration():
    """Example 3: Create a HubSpot integration"""
    print("\n=== Creating HubSpot Integration ===")

    integration_data = {
        "name": "HubSpot CRM",
        "type": "hubspot",
        "credentials": {
            "access_token": "your-hubspot-private-app-token",
            "portal_id": "12345678"
        }
    }

    response = requests.post(
        f"{BASE_URL}/api/integrations",
        headers=headers,
        json=integration_data
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    return response.json().get("integration_id")


def example_4_test_integration(integration_id):
    """Example 4: Test an integration"""
    print(f"\n=== Testing Integration {integration_id} ===")

    response = requests.post(
        f"{BASE_URL}/api/integrations/{integration_id}/test",
        headers=headers
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")


def example_5_create_simple_workflow(jira_integration_id):
    """Example 5: Create a simple workflow - Create Jira ticket after call"""
    print("\n=== Creating Simple Workflow ===")

    workflow_data = {
        "name": "Create Jira Ticket After Call",
        "description": "Automatically create a Jira ticket when a call is completed",
        "trigger_event": "call_completed",
        "conditions": [
            {
                "field": "call.duration",
                "operator": "greater_than",
                "value": 30,
                "logic": "AND"
            }
        ],
        "actions": [
            {
                "type": "create_jira_ticket",
                "integration_id": jira_integration_id,
                "config": {
                    "project": "SUPPORT",
                    "issue_type": "Task",
                    "summary": "Call from {{customer.name}}",
                    "description": "Call Duration: {{call.duration|round:0}} seconds\n\nTranscription:\n{{call.transcription|truncate:500}}",
                    "labels": ["support-call", "automated"]
                },
                "on_error": "continue"
            }
        ],
        "is_active": True,
        "priority": 0
    }

    response = requests.post(
        f"{BASE_URL}/api/workflows",
        headers=headers,
        json=workflow_data
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    return response.json().get("workflow_id")


def example_6_create_advanced_workflow(jira_integration_id, email_integration_id):
    """Example 6: Create advanced workflow - Jira ticket + Email notification"""
    print("\n=== Creating Advanced Workflow ===")

    workflow_data = {
        "name": "Support Call → Jira + Email",
        "description": "Create Jira ticket and send email notification for support calls",
        "trigger_event": "call_completed",
        "conditions": [
            {
                "field": "call.duration",
                "operator": "greater_than",
                "value": 60,
                "logic": "AND"
            },
            {
                "field": "call.status",
                "operator": "equals",
                "value": "completed",
                "logic": "AND"
            }
        ],
        "actions": [
            {
                "id": "create_ticket",
                "type": "create_jira_ticket",
                "integration_id": jira_integration_id,
                "config": {
                    "project": "SUPPORT",
                    "issue_type": "Task",
                    "summary": "Support Call: {{customer.name}}",
                    "description": """Call Details:
- Duration: {{call.duration|round:0}} seconds
- Customer: {{customer.name}}
- Phone: {{customer.phone}}
- Time: {{call.created_at|datetime}}

Transcript:
{{call.transcription}}

Summary:
{{call.summary|default:No summary available}}
""",
                    "labels": ["support-call", "automated"],
                    "priority": "Medium"
                },
                "on_error": "continue",
                "timeout_seconds": 30
            },
            {
                "id": "send_notification",
                "type": "send_email",
                "integration_id": email_integration_id,
                "config": {
                    "to": "{{agent.email}}",
                    "subject": "Jira Ticket Created: {{jira.ticket_key}}",
                    "format": "html",
                    "body": """
<html>
<body>
    <h2>Jira Ticket Created</h2>
    <p>A new Jira ticket has been created for your recent call.</p>

    <p><strong>Ticket:</strong> <a href="{{jira.url}}">{{jira.ticket_key}}</a></p>
    <p><strong>Summary:</strong> {{jira.summary}}</p>

    <h3>Call Details</h3>
    <ul>
        <li><strong>Customer:</strong> {{customer.name}}</li>
        <li><strong>Phone:</strong> {{customer.phone}}</li>
        <li><strong>Duration:</strong> {{call.duration|round:0}} seconds</li>
        <li><strong>Date:</strong> {{call.created_at|datetime}}</li>
    </ul>

    <p>---<br>
    Sent from Convis AI Call System</p>
</body>
</html>
"""
                },
                "on_error": "continue"
            }
        ],
        "is_active": True,
        "priority": 5
    }

    response = requests.post(
        f"{BASE_URL}/api/workflows",
        headers=headers,
        json=workflow_data
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    return response.json().get("workflow_id")


def example_7_manual_trigger_workflow(workflow_id):
    """Example 7: Manually trigger a workflow for testing"""
    print(f"\n=== Manually Triggering Workflow {workflow_id} ===")

    trigger_data = {
        "call": {
            "id": "test-call-123",
            "duration": 120,
            "status": "completed",
            "transcription": "This is a test call transcription. The customer asked about our product pricing.",
            "summary": "Customer inquiry about pricing",
            "created_at": "2024-01-15T10:30:00Z"
        },
        "customer": {
            "name": "John Doe",
            "phone": "+1234567890",
            "email": "john.doe@example.com"
        },
        "agent": {
            "name": "Jane Agent",
            "email": "jane@company.com"
        }
    }

    response = requests.post(
        f"{BASE_URL}/api/workflows/{workflow_id}/execute",
        headers=headers,
        json=trigger_data
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")


def example_8_list_workflows():
    """Example 8: List all workflows"""
    print("\n=== Listing All Workflows ===")

    response = requests.get(
        f"{BASE_URL}/api/workflows",
        headers=headers
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")


def example_9_get_workflow_executions(workflow_id):
    """Example 9: Get workflow execution history"""
    print(f"\n=== Getting Execution History for Workflow {workflow_id} ===")

    response = requests.get(
        f"{BASE_URL}/api/workflows/{workflow_id}/executions",
        headers=headers
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")


def example_10_workflow_statistics():
    """Example 10: Get workflow statistics"""
    print("\n=== Getting Workflow Statistics ===")

    response = requests.get(
        f"{BASE_URL}/api/workflow-stats",
        headers=headers
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")


def example_11_toggle_workflow(workflow_id):
    """Example 11: Toggle workflow active status"""
    print(f"\n=== Toggling Workflow {workflow_id} ===")

    response = requests.post(
        f"{BASE_URL}/api/workflows/{workflow_id}/toggle",
        headers=headers
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")


def run_all_examples():
    """Run all examples in sequence"""
    print("=" * 60)
    print("INTEGRATION SYSTEM EXAMPLES")
    print("=" * 60)

    # Create integrations
    jira_id = example_1_create_jira_integration()
    email_id = example_2_create_email_integration()
    hubspot_id = example_3_create_hubspot_integration()

    # Test an integration
    if jira_id:
        example_4_test_integration(jira_id)

    # Create workflows
    if jira_id:
        simple_workflow_id = example_5_create_simple_workflow(jira_id)

    if jira_id and email_id:
        advanced_workflow_id = example_6_create_advanced_workflow(jira_id, email_id)

    # List workflows
    example_8_list_workflows()

    # Manual trigger (test)
    if simple_workflow_id:
        example_7_manual_trigger_workflow(simple_workflow_id)

    # Get execution history
    if simple_workflow_id:
        example_9_get_workflow_executions(simple_workflow_id)

    # Statistics
    example_10_workflow_statistics()

    print("\n" + "=" * 60)
    print("EXAMPLES COMPLETED!")
    print("=" * 60)


if __name__ == "__main__":
    # Update AUTH_TOKEN at the top of this file first!

    if AUTH_TOKEN == "your-auth-token-here":
        print("ERROR: Please update AUTH_TOKEN in this script first!")
        print("Get your token by logging in to the API")
    else:
        # Run specific example:
        # example_1_create_jira_integration()

        # Or run all examples:
        run_all_examples()

"""
Pytest Configuration and Shared Fixtures
"""
import pytest
from datetime import datetime
from bson import ObjectId
from unittest.mock import Mock


@pytest.fixture
def sample_user_id():
    """Sample user ID for testing"""
    return "user123"


@pytest.fixture
def sample_integration_id():
    """Sample integration ID"""
    return str(ObjectId())


@pytest.fixture
def sample_workflow_id():
    """Sample workflow ID"""
    return str(ObjectId())


@pytest.fixture
def sample_call_data():
    """Complete sample call data"""
    return {
        "_id": str(ObjectId()),
        "status": "completed",
        "duration": 125,
        "direction": "inbound",
        "from_number": "+1234567890",
        "to_number": "+0987654321",
        "transcription": "Customer called about billing issue. Issue was resolved by providing a refund.",
        "summary": "Billing issue resolved with refund",
        "sentiment": "positive",
        "customer_name": "John Doe",
        "customer_email": "john@example.com",
        "customer_phone": "+1234567890",
        "agent_name": "Jane Agent",
        "agent_email": "jane@company.com",
        "recording_url": "https://example.com/recording.mp3",
        "created_at": datetime.utcnow(),
        "ended_at": datetime.utcnow(),
        "metadata": {
            "campaign_id": None,
            "custom_field": "value"
        }
    }


@pytest.fixture
def sample_jira_credentials():
    """Sample Jira credentials"""
    return {
        "base_url": "https://test.atlassian.net",
        "email": "test@example.com",
        "api_token": "test-jira-token",
        "default_project": "TEST",
        "default_issue_type": "Task"
    }


@pytest.fixture
def sample_hubspot_credentials():
    """Sample HubSpot credentials"""
    return {
        "access_token": "test-hubspot-token",
        "portal_id": "12345678"
    }


@pytest.fixture
def sample_email_credentials():
    """Sample Email SMTP credentials"""
    return {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_username": "test@example.com",
        "smtp_password": "test-password",
        "from_email": "test@example.com",
        "from_name": "Test Sender",
        "use_tls": True
    }


@pytest.fixture
def sample_jira_integration(sample_integration_id, sample_user_id, sample_jira_credentials):
    """Complete Jira integration object"""
    return {
        "_id": sample_integration_id,
        "user_id": sample_user_id,
        "name": "Test Jira",
        "type": "jira",
        "credentials": sample_jira_credentials,
        "status": "active",
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "last_tested_at": datetime.utcnow()
    }


@pytest.fixture
def sample_hubspot_integration(sample_integration_id, sample_user_id, sample_hubspot_credentials):
    """Complete HubSpot integration object"""
    return {
        "_id": sample_integration_id,
        "user_id": sample_user_id,
        "name": "Test HubSpot",
        "type": "hubspot",
        "credentials": sample_hubspot_credentials,
        "status": "active",
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }


@pytest.fixture
def sample_email_integration(sample_integration_id, sample_user_id, sample_email_credentials):
    """Complete Email integration object"""
    return {
        "_id": sample_integration_id,
        "user_id": sample_user_id,
        "name": "Test Email",
        "type": "email",
        "credentials": sample_email_credentials,
        "status": "active",
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }


@pytest.fixture
def sample_workflow(sample_workflow_id, sample_user_id, sample_integration_id):
    """Complete workflow object"""
    return {
        "_id": sample_workflow_id,
        "user_id": sample_user_id,
        "name": "Test Workflow",
        "description": "Test workflow for unit tests",
        "trigger_event": "call_completed",
        "trigger_config": None,
        "conditions": [
            {
                "field": "call.duration",
                "operator": "greater_than",
                "value": 60,
                "logic": "AND"
            }
        ],
        "actions": [
            {
                "id": "action1",
                "type": "send_email",
                "integration_id": sample_integration_id,
                "config": {
                    "to": "test@example.com",
                    "subject": "Test Subject",
                    "body": "Test Body"
                },
                "on_error": "continue",
                "retry_count": 0,
                "timeout_seconds": 30
            }
        ],
        "is_active": True,
        "priority": 0,
        "metadata": {},
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "last_executed_at": None,
        "execution_count": 0,
        "success_count": 0,
        "failure_count": 0
    }


@pytest.fixture
def sample_workflow_execution(sample_workflow_id, sample_user_id):
    """Sample workflow execution record"""
    return {
        "_id": str(ObjectId()),
        "workflow_id": sample_workflow_id,
        "user_id": sample_user_id,
        "trigger_event": "call_completed",
        "trigger_data": {
            "call": {"duration": 120}
        },
        "status": "completed",
        "conditions_met": True,
        "actions_executed": [],
        "started_at": datetime.utcnow(),
        "completed_at": datetime.utcnow(),
        "duration_ms": 1500,
        "error_message": None,
        "metadata": {}
    }


@pytest.fixture
def mock_database():
    """Mock MongoDB database"""
    db = Mock()

    # Mock collections
    db.integrations = Mock()
    db.workflows = Mock()
    db.workflow_executions = Mock()
    db.integration_logs = Mock()
    db.workflow_templates = Mock()

    # Mock common methods
    db.integrations.find_one = Mock(return_value=None)
    db.integrations.find = Mock(return_value=[])
    db.integrations.insert_one = Mock()
    db.integrations.update_one = Mock()
    db.integrations.delete_one = Mock()

    db.workflows.find_one = Mock(return_value=None)
    db.workflows.find = Mock(return_value=Mock(sort=Mock(return_value=[])))
    db.workflows.insert_one = Mock()
    db.workflows.update_one = Mock()
    db.workflows.delete_one = Mock()

    db.workflow_executions.find_one = Mock(return_value=None)
    db.workflow_executions.find = Mock(return_value=Mock(sort=Mock(return_value=[])))
    db.workflow_executions.insert_one = Mock()

    db.integration_logs.insert_one = Mock()
    db.integration_logs.find = Mock(return_value=Mock(sort=Mock(return_value=[])))

    return db


@pytest.fixture
def mock_authenticated_user():
    """Mock authenticated user for route testing"""
    user = Mock()
    user.id = "user123"
    user.email = "test@example.com"
    user.name = "Test User"
    return user


# Pytest configuration
def pytest_configure(config):
    """Configure pytest"""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires database)"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as unit test (mocked dependencies)"
    )
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test"
    )

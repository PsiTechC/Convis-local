"""
Database Setup for Integrations
Creates indexes and initializes collections
"""
import logging
from app.config.database import Database

logger = logging.getLogger(__name__)


def setup_integration_indexes():
    """Create database indexes for integrations and workflows"""
    try:
        db = Database.get_db()

        logger.info("Creating integration system indexes...")

        # Integrations collection indexes
        db.integrations.create_index([("user_id", 1), ("type", 1)])
        db.integrations.create_index([("user_id", 1), ("is_active", 1)])
        db.integrations.create_index([("created_at", -1)])

        # Workflows collection indexes
        db.workflows.create_index([("user_id", 1), ("trigger_event", 1)])
        db.workflows.create_index([("user_id", 1), ("is_active", 1)])
        db.workflows.create_index([("trigger_event", 1), ("is_active", 1)])
        db.workflows.create_index([("created_at", -1)])
        db.workflows.create_index([("priority", -1)])

        # Workflow executions collection indexes
        db.workflow_executions.create_index([("workflow_id", 1), ("started_at", -1)])
        db.workflow_executions.create_index([("user_id", 1), ("started_at", -1)])
        db.workflow_executions.create_index([("status", 1)])
        db.workflow_executions.create_index([("trigger_event", 1)])
        db.workflow_executions.create_index([("call_id", 1)])
        db.workflow_executions.create_index([("campaign_id", 1)])

        # Integration logs collection indexes
        db.integration_logs.create_index([("integration_id", 1), ("created_at", -1)])
        db.integration_logs.create_index([("workflow_execution_id", 1)])
        db.integration_logs.create_index([("status", 1)])
        db.integration_logs.create_index([("created_at", -1)])

        # Create TTL index for old logs (optional - delete logs older than 90 days)
        db.integration_logs.create_index(
            [("created_at", 1)],
            expireAfterSeconds=7776000  # 90 days
        )

        logger.info("Integration system indexes created successfully")

    except Exception as e:
        logger.error(f"Error creating indexes: {e}")
        raise


def initialize_workflow_templates():
    """Initialize default workflow templates"""
    try:
        db = Database.get_db()

        logger.info("Initializing workflow templates...")

        # Template 1: Call completed -> Create Jira ticket + Send email
        template1 = {
            "name": "Create Jira Ticket for Support Calls",
            "description": "Automatically create a Jira ticket and send email notification when a support call is completed",
            "category": "customer_support",
            "icon": "ticket",
            "trigger_event": "call_completed",
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
                    "type": "create_jira_ticket",
                    "integration_id": None,  # User must select their integration
                    "config": {
                        "project": "SUPPORT",
                        "issue_type": "Task",
                        "summary": "Support Call: {{customer.name}}",
                        "description": "Call Duration: {{call.duration|round:0}} seconds\n\nTranscript:\n{{call.transcription}}",
                        "labels": ["support-call", "automated"]
                    },
                    "on_error": "continue"
                },
                {
                    "type": "send_email",
                    "integration_id": None,
                    "config": {
                        "to": "{{agent.email}}",
                        "subject": "Jira Ticket Created: {{jira.ticket_key}}",
                        "body": "A Jira ticket has been created for your recent call with {{customer.name}}.\n\nTicket: {{jira.url}}\nDuration: {{call.duration|round:0}} seconds"
                    },
                    "on_error": "continue"
                }
            ],
            "required_integrations": ["jira", "email"],
            "is_public": True
        }

        # Template 2: Call completed -> Update HubSpot + Send email
        template2 = {
            "name": "Log Call in HubSpot CRM",
            "description": "Automatically create or update HubSpot contact and add call notes when a call is completed",
            "category": "sales",
            "icon": "contacts",
            "trigger_event": "call_completed",
            "conditions": [],
            "actions": [
                {
                    "type": "create_hubspot_contact",
                    "integration_id": None,
                    "config": {
                        "email": "{{customer.email}}",
                        "firstname": "{{customer.name|split: |first}}",
                        "phone": "{{customer.phone}}",
                        "update_if_exists": True
                    },
                    "on_error": "continue"
                },
                {
                    "type": "create_hubspot_note",
                    "integration_id": None,
                    "config": {
                        "contact_email": "{{customer.email}}",
                        "note_body": "Call completed on {{call.created_at|date}}\nDuration: {{call.duration|round:0}} seconds\n\nSummary:\n{{call.summary}}"
                    },
                    "on_error": "continue"
                }
            ],
            "required_integrations": ["hubspot"],
            "is_public": True
        }

        # Template 3: Failed call -> Send alert email
        template3 = {
            "name": "Alert on Failed Calls",
            "description": "Send email alert when a call fails",
            "category": "monitoring",
            "icon": "alert",
            "trigger_event": "call_failed",
            "conditions": [],
            "actions": [
                {
                    "type": "send_email",
                    "integration_id": None,
                    "config": {
                        "to": "{{agent.email}}",
                        "subject": "Call Failed Alert",
                        "body": "A call to {{customer.phone}} failed.\n\nError: {{call.error}}\nTime: {{timestamp|datetime}}"
                    },
                    "on_error": "continue"
                }
            ],
            "required_integrations": ["email"],
            "is_public": True
        }

        templates = [template1, template2, template3]

        for template in templates:
            # Check if template already exists
            existing = db.workflow_templates.find_one({"name": template["name"]})
            if not existing:
                from datetime import datetime
                template["created_at"] = datetime.utcnow()
                template["usage_count"] = 0
                db.workflow_templates.insert_one(template)
                logger.info(f"Created template: {template['name']}")

        logger.info("Workflow templates initialized")

    except Exception as e:
        logger.error(f"Error initializing templates: {e}")


if __name__ == "__main__":
    # Run setup
    setup_integration_indexes()
    initialize_workflow_templates()
    print("Integration system setup completed!")

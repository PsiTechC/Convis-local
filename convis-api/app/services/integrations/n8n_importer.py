"""
n8n Workflow Importer
Converts n8n workflow JSON exports to Convis visual workflow format
"""
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from bson import ObjectId

logger = logging.getLogger(__name__)


class N8nImporter:
    """
    Imports n8n workflow JSON and converts to Convis workflow format.

    n8n workflow structure:
    {
        "name": "Workflow Name",
        "nodes": [...],
        "connections": {...},
        "settings": {...},
        "staticData": {...}
    }

    Convis workflow structure:
    {
        "name": "Workflow Name",
        "graph_data": {
            "nodes": [...],
            "edges": [...]
        }
    }
    """

    # Map n8n node types to Convis node types
    NODE_TYPE_MAP = {
        # Triggers
        "n8n-nodes-base.webhook": {"type": "trigger", "triggerType": "webhook", "label": "Webhook", "icon": "🔗"},
        "n8n-nodes-base.scheduleTrigger": {"type": "trigger", "triggerType": "schedule", "label": "Schedule", "icon": "⏰"},
        "n8n-nodes-base.manualTrigger": {"type": "trigger", "triggerType": "manual", "label": "Manual Trigger", "icon": "▶️"},
        "n8n-nodes-base.emailTrigger": {"type": "trigger", "triggerType": "email_received", "label": "Email Trigger", "icon": "📥"},
        "n8n-nodes-base.cronTrigger": {"type": "trigger", "triggerType": "schedule", "label": "Cron", "icon": "⏰"},

        # Communication
        "n8n-nodes-base.gmail": {"type": "action", "actionType": "gmail", "label": "Gmail", "icon": "📧", "category": "Communication"},
        "n8n-nodes-base.emailSend": {"type": "action", "actionType": "send_email", "label": "Send Email", "icon": "📧", "category": "Communication"},
        "n8n-nodes-base.slack": {"type": "action", "actionType": "slack", "label": "Slack", "icon": "💬", "category": "Communication"},
        "n8n-nodes-base.discord": {"type": "action", "actionType": "discord", "label": "Discord", "icon": "🎮", "category": "Communication"},
        "n8n-nodes-base.telegram": {"type": "action", "actionType": "telegram", "label": "Telegram", "icon": "✈️", "category": "Communication"},
        "n8n-nodes-base.microsoftTeams": {"type": "action", "actionType": "teams", "label": "Teams", "icon": "👥", "category": "Communication"},
        "n8n-nodes-base.twilio": {"type": "action", "actionType": "twilio_sms", "label": "Twilio SMS", "icon": "📱", "category": "Communication"},
        "n8n-nodes-base.sendGrid": {"type": "action", "actionType": "sendgrid", "label": "SendGrid", "icon": "📨", "category": "Communication"},

        # Project Management
        "n8n-nodes-base.jira": {"type": "action", "actionType": "jira_create", "label": "Jira", "icon": "🎫", "category": "Project Management"},
        "n8n-nodes-base.jiraSoftware": {"type": "action", "actionType": "jira_create", "label": "Jira Software", "icon": "🎫", "category": "Project Management"},
        "n8n-nodes-base.asana": {"type": "action", "actionType": "asana", "label": "Asana", "icon": "✅", "category": "Project Management"},
        "n8n-nodes-base.trello": {"type": "action", "actionType": "trello", "label": "Trello", "icon": "📋", "category": "Project Management"},
        "n8n-nodes-base.notion": {"type": "action", "actionType": "notion", "label": "Notion", "icon": "📝", "category": "Project Management"},
        "n8n-nodes-base.linear": {"type": "action", "actionType": "linear", "label": "Linear", "icon": "📐", "category": "Project Management"},
        "n8n-nodes-base.clickUp": {"type": "action", "actionType": "clickup", "label": "ClickUp", "icon": "✓", "category": "Project Management"},
        "n8n-nodes-base.github": {"type": "action", "actionType": "github", "label": "GitHub", "icon": "🐙", "category": "Project Management"},
        "n8n-nodes-base.gitlab": {"type": "action", "actionType": "gitlab", "label": "GitLab", "icon": "🦊", "category": "Project Management"},

        # CRM
        "n8n-nodes-base.hubspot": {"type": "action", "actionType": "hubspot_contact", "label": "HubSpot", "icon": "🧡", "category": "CRM"},
        "n8n-nodes-base.salesforce": {"type": "action", "actionType": "salesforce", "label": "Salesforce", "icon": "☁️", "category": "CRM"},
        "n8n-nodes-base.pipedrive": {"type": "action", "actionType": "pipedrive", "label": "Pipedrive", "icon": "💼", "category": "CRM"},
        "n8n-nodes-base.zoho": {"type": "action", "actionType": "zoho", "label": "Zoho CRM", "icon": "📊", "category": "CRM"},

        # Database
        "n8n-nodes-base.postgres": {"type": "action", "actionType": "postgres", "label": "PostgreSQL", "icon": "🐘", "category": "Database"},
        "n8n-nodes-base.mysql": {"type": "action", "actionType": "mysql", "label": "MySQL", "icon": "🐬", "category": "Database"},
        "n8n-nodes-base.mongodb": {"type": "action", "actionType": "mongodb", "label": "MongoDB", "icon": "🍃", "category": "Database"},
        "n8n-nodes-base.redis": {"type": "action", "actionType": "redis", "label": "Redis", "icon": "🔴", "category": "Database"},
        "n8n-nodes-base.airtable": {"type": "action", "actionType": "airtable", "label": "Airtable", "icon": "📊", "category": "Database"},
        "n8n-nodes-base.googleSheets": {"type": "action", "actionType": "google_sheets", "label": "Google Sheets", "icon": "📗", "category": "Database"},
        "n8n-nodes-base.supabase": {"type": "action", "actionType": "supabase", "label": "Supabase", "icon": "⚡", "category": "Database"},

        # AI
        "n8n-nodes-base.openAi": {"type": "action", "actionType": "openai", "label": "OpenAI", "icon": "🤖", "category": "AI"},
        "@n8n/n8n-nodes-langchain.openAi": {"type": "action", "actionType": "openai", "label": "OpenAI", "icon": "🤖", "category": "AI"},
        "n8n-nodes-base.anthropic": {"type": "action", "actionType": "anthropic", "label": "Claude", "icon": "🧠", "category": "AI"},

        # HTTP/Webhooks
        "n8n-nodes-base.httpRequest": {"type": "action", "actionType": "http_request", "label": "HTTP Request", "icon": "🌐", "category": "HTTP"},
        "n8n-nodes-base.respondToWebhook": {"type": "action", "actionType": "respond_webhook", "label": "Respond", "icon": "↩️", "category": "HTTP"},

        # Flow Control
        "n8n-nodes-base.if": {"type": "condition", "conditionType": "if", "label": "IF", "icon": "🔀"},
        "n8n-nodes-base.switch": {"type": "condition", "conditionType": "switch", "label": "Switch", "icon": "🔀"},
        "n8n-nodes-base.merge": {"type": "utility", "utilityType": "merge", "label": "Merge", "icon": "🔗"},
        "n8n-nodes-base.splitInBatches": {"type": "utility", "utilityType": "split", "label": "Split", "icon": "✂️"},
        "n8n-nodes-base.wait": {"type": "utility", "utilityType": "delay", "label": "Wait", "icon": "⏳"},
        "n8n-nodes-base.noOp": {"type": "utility", "utilityType": "noop", "label": "No Op", "icon": "⏹️"},

        # Data Transform
        "n8n-nodes-base.set": {"type": "transform", "transformType": "set", "label": "Set", "icon": "📝"},
        "n8n-nodes-base.code": {"type": "transform", "transformType": "code", "label": "Code", "icon": "💻"},
        "n8n-nodes-base.function": {"type": "transform", "transformType": "function", "label": "Function", "icon": "ƒ"},
        "n8n-nodes-base.functionItem": {"type": "transform", "transformType": "function_item", "label": "Function Item", "icon": "ƒ"},
        "n8n-nodes-base.itemLists": {"type": "transform", "transformType": "item_lists", "label": "Item Lists", "icon": "📋"},
        "n8n-nodes-base.filter": {"type": "transform", "transformType": "filter", "label": "Filter", "icon": "🔍"},
        "n8n-nodes-base.sort": {"type": "transform", "transformType": "sort", "label": "Sort", "icon": "↕️"},
        "n8n-nodes-base.limit": {"type": "transform", "transformType": "limit", "label": "Limit", "icon": "🔢"},
        "n8n-nodes-base.removeDuplicates": {"type": "transform", "transformType": "dedupe", "label": "Remove Duplicates", "icon": "🧹"},
        "n8n-nodes-base.spreadsheetFile": {"type": "transform", "transformType": "spreadsheet", "label": "Spreadsheet", "icon": "📊"},
        "n8n-nodes-base.xml": {"type": "transform", "transformType": "xml", "label": "XML", "icon": "📄"},
        "n8n-nodes-base.html": {"type": "transform", "transformType": "html", "label": "HTML", "icon": "🌐"},
        "n8n-nodes-base.markdown": {"type": "transform", "transformType": "markdown", "label": "Markdown", "icon": "📝"},

        # Calendar
        "n8n-nodes-base.googleCalendar": {"type": "action", "actionType": "google_calendar", "label": "Google Calendar", "icon": "📅", "category": "Calendar"},
        "n8n-nodes-base.calendly": {"type": "action", "actionType": "calendly", "label": "Calendly", "icon": "📆", "category": "Calendar"},

        # Storage
        "n8n-nodes-base.s3": {"type": "action", "actionType": "aws_s3", "label": "AWS S3", "icon": "📦", "category": "Storage"},
        "n8n-nodes-base.googleDrive": {"type": "action", "actionType": "google_drive", "label": "Google Drive", "icon": "📁", "category": "Storage"},
        "n8n-nodes-base.dropbox": {"type": "action", "actionType": "dropbox", "label": "Dropbox", "icon": "📥", "category": "Storage"},

        # Payment
        "n8n-nodes-base.stripe": {"type": "action", "actionType": "stripe", "label": "Stripe", "icon": "💳", "category": "Payment"},
        "n8n-nodes-base.paypal": {"type": "action", "actionType": "paypal", "label": "PayPal", "icon": "💰", "category": "Payment"},
    }

    # Default node for unknown types
    DEFAULT_NODE = {"type": "action", "actionType": "custom", "label": "Custom Node", "icon": "⚙️", "category": "Custom"}

    @classmethod
    def parse_n8n_json(cls, json_data: str) -> Dict[str, Any]:
        """Parse n8n JSON string to dict"""
        try:
            if isinstance(json_data, str):
                return json.loads(json_data)
            return json_data
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {e}")

    @classmethod
    def get_node_mapping(cls, n8n_type: str) -> Dict[str, Any]:
        """Get Convis node mapping for n8n node type"""
        return cls.NODE_TYPE_MAP.get(n8n_type, cls.DEFAULT_NODE.copy())

    @classmethod
    def convert_position(cls, n8n_position: List[int]) -> Dict[str, int]:
        """Convert n8n position [x, y] to Convis position {x, y}"""
        if n8n_position and len(n8n_position) >= 2:
            return {"x": n8n_position[0], "y": n8n_position[1]}
        return {"x": 100, "y": 100}

    @classmethod
    def extract_node_config(cls, n8n_node: Dict[str, Any]) -> Dict[str, Any]:
        """Extract configuration from n8n node parameters"""
        config = {}
        params = n8n_node.get("parameters", {})

        n8n_type = n8n_node.get("type", "")

        # Handle different node types
        if "jira" in n8n_type.lower():
            config = {
                "project": params.get("project"),
                "issueType": params.get("issueType"),
                "summary": params.get("summary"),
                "description": params.get("description"),
                "priority": params.get("priority"),
                "labels": params.get("labels"),
                "assignee": params.get("assignee"),
            }

        elif "gmail" in n8n_type.lower() or "email" in n8n_type.lower():
            config = {
                "to": params.get("toRecipients") or params.get("to"),
                "subject": params.get("subject"),
                "body": params.get("message") or params.get("body") or params.get("text"),
                "cc": params.get("ccRecipients") or params.get("cc"),
                "bcc": params.get("bccRecipients") or params.get("bcc"),
            }

        elif "slack" in n8n_type.lower():
            config = {
                "channel": params.get("channel"),
                "message": params.get("text") or params.get("message"),
                "username": params.get("username"),
            }

        elif "hubspot" in n8n_type.lower():
            config = {
                "resource": params.get("resource"),
                "operation": params.get("operation"),
                "email": params.get("email"),
                "firstName": params.get("firstName"),
                "lastName": params.get("lastName"),
                "properties": params.get("additionalFields"),
            }

        elif "httpRequest" in n8n_type:
            config = {
                "url": params.get("url"),
                "method": params.get("method", "GET"),
                "headers": params.get("headerParameters"),
                "body": params.get("body") or params.get("bodyParameters"),
                "authentication": params.get("authentication"),
            }

        elif "if" in n8n_type.lower():
            conditions = params.get("conditions", {})
            config = {
                "conditions": conditions,
                "combineOperation": params.get("combineOperation", "all"),
            }

        elif "code" in n8n_type.lower() or "function" in n8n_type.lower():
            config = {
                "code": params.get("jsCode") or params.get("functionCode") or params.get("code"),
                "language": params.get("language", "javascript"),
            }

        elif "set" in n8n_type.lower():
            config = {
                "values": params.get("values") or params.get("assignments"),
                "mode": params.get("mode", "manual"),
            }

        elif "wait" in n8n_type.lower():
            config = {
                "amount": params.get("amount", 1),
                "unit": params.get("unit", "seconds"),
            }

        elif "openai" in n8n_type.lower() or "openAi" in n8n_type.lower():
            config = {
                "model": params.get("model"),
                "prompt": params.get("prompt") or params.get("text"),
                "temperature": params.get("temperature"),
                "maxTokens": params.get("maxTokens"),
                "operation": params.get("operation"),
            }

        elif "webhook" in n8n_type.lower():
            config = {
                "path": params.get("path"),
                "httpMethod": params.get("httpMethod", "GET"),
                "responseMode": params.get("responseMode"),
            }

        else:
            # Generic parameter extraction
            config = {k: v for k, v in params.items() if v is not None}

        # Remove None values
        config = {k: v for k, v in config.items() if v is not None}

        return config

    @classmethod
    def convert_node(cls, n8n_node: Dict[str, Any], index: int) -> Dict[str, Any]:
        """Convert a single n8n node to Convis format"""
        n8n_type = n8n_node.get("type", "")
        node_name = n8n_node.get("name", f"Node_{index}")
        position = n8n_node.get("position", [100 + index * 200, 100])

        # Get mapping
        mapping = cls.get_node_mapping(n8n_type)

        # Build Convis node
        convis_node = {
            "id": n8n_node.get("id") or f"node_{index}",
            "type": mapping["type"],
            "position": cls.convert_position(position),
            "data": {
                "label": node_name,
                "icon": mapping.get("icon", "⚙️"),
                "description": f"Imported from n8n: {n8n_type}",
                "config": cls.extract_node_config(n8n_node),
                "n8n_type": n8n_type,  # Store original type for reference
                "category": mapping.get("category", "Custom"),
            }
        }

        # Add type-specific fields
        if mapping["type"] == "trigger":
            convis_node["data"]["triggerType"] = mapping.get("triggerType", "manual")
        elif mapping["type"] == "action":
            convis_node["data"]["actionType"] = mapping.get("actionType", "custom")
        elif mapping["type"] == "condition":
            convis_node["data"]["conditionType"] = mapping.get("conditionType", "if")
        elif mapping["type"] == "transform":
            convis_node["data"]["transformType"] = mapping.get("transformType", "custom")
        elif mapping["type"] == "utility":
            convis_node["data"]["utilityType"] = mapping.get("utilityType", "custom")

        return convis_node

    @classmethod
    def convert_connections(cls, n8n_connections: Dict[str, Any], node_name_to_id: Dict[str, str]) -> List[Dict[str, Any]]:
        """Convert n8n connections to Convis edges"""
        edges = []
        edge_index = 0

        # n8n connections format:
        # {
        #     "Node Name": {
        #         "main": [
        #             [{"node": "Target Node", "type": "main", "index": 0}]
        #         ]
        #     }
        # }

        for source_name, outputs in n8n_connections.items():
            source_id = node_name_to_id.get(source_name)
            if not source_id:
                continue

            for output_type, output_connections in outputs.items():
                for output_index, connections in enumerate(output_connections):
                    for conn in connections:
                        target_name = conn.get("node")
                        target_id = node_name_to_id.get(target_name)

                        if target_id:
                            edge = {
                                "id": f"edge_{edge_index}",
                                "source": source_id,
                                "target": target_id,
                                "sourceHandle": f"output_{output_index}" if output_index > 0 else None,
                                "targetHandle": f"input_{conn.get('index', 0)}" if conn.get('index', 0) > 0 else None,
                                "type": "smoothstep",
                                "animated": True,
                            }
                            edges.append(edge)
                            edge_index += 1

        return edges

    @classmethod
    def extract_credentials_info(cls, n8n_workflow: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract credential requirements from n8n workflow"""
        credentials_needed = []
        seen_creds = set()

        for node in n8n_workflow.get("nodes", []):
            creds = node.get("credentials", {})
            for cred_type, cred_info in creds.items():
                cred_name = cred_info.get("name", cred_type) if isinstance(cred_info, dict) else cred_info
                cred_key = f"{cred_type}:{cred_name}"

                if cred_key not in seen_creds:
                    seen_creds.add(cred_key)

                    # Map n8n credential types to Convis integration types
                    integration_type = cls._map_credential_type(cred_type)

                    credentials_needed.append({
                        "n8n_type": cred_type,
                        "name": cred_name,
                        "integration_type": integration_type,
                        "required_for_nodes": [node.get("name")]
                    })

        return credentials_needed

    @classmethod
    def _map_credential_type(cls, n8n_cred_type: str) -> str:
        """Map n8n credential type to Convis integration type"""
        cred_map = {
            "jiraApi": "jira",
            "jiraSoftwareCloudApi": "jira",
            "jiraSoftwareServerApi": "jira",
            "hubspotApi": "hubspot",
            "hubspotOAuth2Api": "hubspot",
            "gmailOAuth2": "gmail",
            "googleOAuth2Api": "google_calendar",
            "slackApi": "slack",
            "slackOAuth2Api": "slack",
            "discordApi": "discord",
            "discordWebhookApi": "discord",
            "telegramApi": "telegram",
            "microsoftTeamsOAuth2Api": "teams",
            "twilioApi": "twilio",
            "sendGridApi": "sendgrid",
            "notionApi": "notion",
            "asanaApi": "asana",
            "trelloApi": "trello",
            "githubApi": "github",
            "gitlabApi": "gitlab",
            "linearApi": "linear",
            "clickUpApi": "clickup",
            "salesforceOAuth2Api": "salesforce",
            "pipedriveApi": "pipedrive",
            "openAiApi": "openai",
            "anthropicApi": "anthropic",
            "postgresApi": "postgresql",
            "mysqlApi": "mysql",
            "mongoDbApi": "mongodb",
            "airtableApi": "airtable",
            "googleSheetsOAuth2Api": "google_sheets",
            "supabaseApi": "supabase",
            "stripeApi": "stripe",
            "paypalApi": "paypal",
            "awsS3": "aws_s3",
            "googleDriveOAuth2Api": "google_drive",
            "dropboxOAuth2Api": "dropbox",
            "calendlyApi": "calendly",
            "httpBasicAuth": "api_key",
            "httpHeaderAuth": "api_key",
        }

        return cred_map.get(n8n_cred_type, "webhook")

    @classmethod
    def import_workflow(
        cls,
        n8n_json: str | Dict[str, Any],
        user_id: str,
        workflow_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Import n8n workflow and convert to Convis format

        Args:
            n8n_json: n8n workflow JSON (string or dict)
            user_id: User ID for the imported workflow
            workflow_name: Optional override for workflow name

        Returns:
            Convis workflow dict ready to save
        """
        # Parse JSON if string
        if isinstance(n8n_json, str):
            n8n_workflow = cls.parse_n8n_json(n8n_json)
        else:
            n8n_workflow = n8n_json

        # Extract basic info
        name = workflow_name or n8n_workflow.get("name", "Imported n8n Workflow")
        n8n_nodes = n8n_workflow.get("nodes", [])
        n8n_connections = n8n_workflow.get("connections", {})

        # Build node name to ID mapping
        node_name_to_id = {}
        convis_nodes = []

        for index, n8n_node in enumerate(n8n_nodes):
            convis_node = cls.convert_node(n8n_node, index)
            convis_nodes.append(convis_node)
            node_name_to_id[n8n_node.get("name")] = convis_node["id"]

        # Convert connections to edges
        convis_edges = cls.convert_connections(n8n_connections, node_name_to_id)

        # Extract credentials info
        credentials_info = cls.extract_credentials_info(n8n_workflow)

        # Determine trigger type from first trigger node
        trigger_event = "manual"
        for node in convis_nodes:
            if node["type"] == "trigger":
                trigger_event = node["data"].get("triggerType", "manual")
                break

        # Build Convis workflow
        convis_workflow = {
            "name": name,
            "description": f"Imported from n8n workflow: {n8n_workflow.get('name', 'Unknown')}",
            "user_id": user_id,
            "trigger_event": trigger_event,
            "is_active": False,  # Start disabled, user should configure credentials first
            "priority": 0,
            "graph_data": {
                "nodes": convis_nodes,
                "edges": convis_edges
            },
            "metadata": {
                "imported_from": "n8n",
                "original_name": n8n_workflow.get("name"),
                "import_date": datetime.utcnow().isoformat(),
                "n8n_id": n8n_workflow.get("id"),
                "credentials_required": credentials_info,
                "node_count": len(convis_nodes),
                "edge_count": len(convis_edges),
            },
            "conditions": [],
            "actions": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        return convis_workflow

    @classmethod
    def validate_n8n_json(cls, json_data: str | Dict) -> Tuple[bool, str, Optional[Dict]]:
        """
        Validate n8n workflow JSON

        Returns:
            (is_valid, message, parsed_data)
        """
        try:
            if isinstance(json_data, str):
                data = json.loads(json_data)
            else:
                data = json_data

            # Check required fields
            if "nodes" not in data:
                return False, "Missing 'nodes' field in workflow", None

            if not isinstance(data["nodes"], list):
                return False, "'nodes' must be an array", None

            if len(data["nodes"]) == 0:
                return False, "Workflow has no nodes", None

            # Validate nodes have required fields
            for i, node in enumerate(data["nodes"]):
                if "type" not in node:
                    return False, f"Node {i} missing 'type' field", None
                if "name" not in node:
                    return False, f"Node {i} missing 'name' field", None

            return True, f"Valid n8n workflow with {len(data['nodes'])} nodes", data

        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}", None
        except Exception as e:
            return False, f"Validation error: {e}", None


# Singleton instance
n8n_importer = N8nImporter()

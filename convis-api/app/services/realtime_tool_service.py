"""
Realtime Tool Service - Vapi-like tool/function calling during voice calls

This service enables the AI to call external APIs, webhooks, and perform actions
during an active voice conversation, similar to Vapi's real-time tool calling.

Tool Types Supported:
1. WEBHOOK - Call external HTTP endpoints
2. DATABASE_QUERY - Query the database
3. CREATE_TICKET - Create Jira/support tickets
4. SEND_NOTIFICATION - Send Slack/email notifications
5. CALENDAR_CHECK - Check calendar availability
6. CUSTOM_FUNCTION - Execute custom logic
"""

import asyncio
import aiohttp
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class RealtimeToolService:
    """
    Service for executing tools during active voice calls.

    This enables Vapi-like functionality where the AI can:
    - Look up customer information mid-call
    - Create tickets while talking
    - Check calendar availability in real-time
    - Call webhooks to trigger external actions
    - Query databases for information
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        assistant_id: Optional[str] = None,
        call_id: Optional[str] = None,
        db=None
    ):
        self.user_id = user_id
        self.assistant_id = assistant_id
        self.call_id = call_id
        self.db = db
        self.tool_execution_log: List[Dict] = []

    def get_openai_tools_schema(self, tool_configs: List[Dict]) -> List[Dict]:
        """
        Convert tool configurations to OpenAI function calling format.

        Args:
            tool_configs: List of tool configurations from assistant config

        Returns:
            List of tools in OpenAI format for chat.completions.create()
        """
        openai_tools = []

        for tool in tool_configs:
            tool_type = tool.get("type", "function")

            if tool_type == "function":
                # Standard function format
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name"),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {
                            "type": "object",
                            "properties": {},
                            "required": []
                        })
                    }
                })
            elif tool_type == "webhook":
                # Webhook tool - expose as function
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name", "call_webhook"),
                        "description": tool.get("description", "Call an external webhook"),
                        "parameters": tool.get("parameters", {
                            "type": "object",
                            "properties": {},
                            "required": []
                        })
                    }
                })
            elif tool_type == "database_query":
                # Database query tool
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name", "query_database"),
                        "description": tool.get("description", "Query the database for information"),
                        "parameters": tool.get("parameters", {
                            "type": "object",
                            "properties": {
                                "query_type": {
                                    "type": "string",
                                    "description": "Type of query to perform"
                                },
                                "filters": {
                                    "type": "object",
                                    "description": "Query filters"
                                }
                            },
                            "required": ["query_type"]
                        })
                    }
                })

        return openai_tools

    async def execute_tool(
        self,
        tool_name: str,
        tool_arguments: Dict[str, Any],
        tool_configs: List[Dict],
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Execute a tool call and return the result.

        Args:
            tool_name: Name of the tool to execute
            tool_arguments: Arguments passed to the tool
            tool_configs: List of tool configurations from assistant
            context: Additional context (call_id, conversation, etc.)

        Returns:
            Tool execution result
        """
        start_time = datetime.now()

        try:
            # Find the tool configuration
            tool_config = None
            for tc in tool_configs:
                if tc.get("name") == tool_name:
                    tool_config = tc
                    break

            if not tool_config:
                return {
                    "success": False,
                    "error": f"Tool '{tool_name}' not found in configuration"
                }

            tool_type = tool_config.get("type", "function")

            # Execute based on tool type
            if tool_type == "webhook":
                result = await self._execute_webhook(tool_config, tool_arguments, context)
            elif tool_type == "database_query":
                result = await self._execute_database_query(tool_config, tool_arguments, context)
            elif tool_type == "create_ticket":
                result = await self._execute_create_ticket(tool_config, tool_arguments, context)
            elif tool_type == "send_notification":
                result = await self._execute_send_notification(tool_config, tool_arguments, context)
            elif tool_type == "calendar_check":
                result = await self._execute_calendar_check(tool_config, tool_arguments, context)
            elif tool_type == "function":
                # Custom function - call the webhook URL if provided
                if tool_config.get("server", {}).get("url"):
                    result = await self._execute_webhook(tool_config, tool_arguments, context)
                else:
                    result = await self._execute_custom_function(tool_config, tool_arguments, context)
            else:
                result = {
                    "success": False,
                    "error": f"Unknown tool type: {tool_type}"
                }

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            # Log execution
            self.tool_execution_log.append({
                "tool_name": tool_name,
                "tool_type": tool_type,
                "arguments": tool_arguments,
                "result": result,
                "execution_time_ms": execution_time,
                "timestamp": datetime.now().isoformat()
            })

            logger.info(f"[REALTIME-TOOL] ✅ Executed {tool_name} in {execution_time:.0f}ms")
            return result

        except Exception as e:
            logger.error(f"[REALTIME-TOOL] ❌ Error executing {tool_name}: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def _execute_webhook(
        self,
        tool_config: Dict,
        arguments: Dict,
        context: Optional[Dict]
    ) -> Dict[str, Any]:
        """Execute a webhook/HTTP call"""
        # Get URL from server config (Vapi-style) or direct url field
        server_config = tool_config.get("server", {})
        url = server_config.get("url") or tool_config.get("url")

        if not url:
            return {"success": False, "error": "No webhook URL configured"}

        method = tool_config.get("method", "POST").upper()
        headers = tool_config.get("headers", {})
        timeout = tool_config.get("timeout", 30)

        # Add secret header if configured (Vapi-style)
        if server_config.get("secret"):
            headers["x-vapi-secret"] = server_config["secret"]

        # Build request body with Vapi-like structure
        body = {
            "message": {
                "type": "tool-calls",
                "toolCallList": [{
                    "id": f"call_{datetime.now().timestamp()}",
                    "type": "function",
                    "function": {
                        "name": tool_config.get("name"),
                        "arguments": arguments
                    }
                }],
                "call": {
                    "id": self.call_id,
                    "assistantId": self.assistant_id
                }
            }
        }

        # If custom body template exists, use it
        if tool_config.get("body_template"):
            body = self._render_template(tool_config["body_template"], {
                **arguments,
                "call_id": self.call_id,
                "assistant_id": self.assistant_id,
                **(context or {})
            })

        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=method,
                    url=url,
                    json=body,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    response_text = await response.text()

                    # Try to parse as JSON
                    try:
                        response_data = json.loads(response_text)
                    except json.JSONDecodeError:
                        response_data = {"raw_response": response_text}

                    # Extract result in Vapi format
                    if isinstance(response_data, dict):
                        # Check for results array (Vapi format)
                        if "results" in response_data and response_data["results"]:
                            result_content = response_data["results"][0].get("result", response_data)
                        else:
                            result_content = response_data.get("result", response_data)
                    else:
                        result_content = response_data

                    return {
                        "success": response.status in [200, 201, 202],
                        "status_code": response.status,
                        "data": result_content
                    }

        except asyncio.TimeoutError:
            return {"success": False, "error": "Webhook request timed out"}
        except aiohttp.ClientError as e:
            return {"success": False, "error": f"HTTP error: {str(e)}"}

    async def _execute_database_query(
        self,
        tool_config: Dict,
        arguments: Dict,
        context: Optional[Dict]
    ) -> Dict[str, Any]:
        """Execute a database query"""
        if not self.db:
            return {"success": False, "error": "Database not available"}

        try:
            collection_name = tool_config.get("collection") or arguments.get("collection")
            query_type = arguments.get("query_type", "find")
            filters = arguments.get("filters", {})
            limit = arguments.get("limit", 10)

            if not collection_name:
                return {"success": False, "error": "Collection name required"}

            collection = self.db[collection_name]

            if query_type == "find":
                cursor = collection.find(filters).limit(limit)
                results = await cursor.to_list(length=limit)
                # Convert ObjectId to string
                for doc in results:
                    if "_id" in doc:
                        doc["_id"] = str(doc["_id"])
                return {"success": True, "data": results, "count": len(results)}

            elif query_type == "find_one":
                result = await collection.find_one(filters)
                if result and "_id" in result:
                    result["_id"] = str(result["_id"])
                return {"success": True, "data": result}

            elif query_type == "count":
                count = await collection.count_documents(filters)
                return {"success": True, "count": count}

            else:
                return {"success": False, "error": f"Unknown query type: {query_type}"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _execute_create_ticket(
        self,
        tool_config: Dict,
        arguments: Dict,
        context: Optional[Dict]
    ) -> Dict[str, Any]:
        """Create a support ticket (Jira, etc.)"""
        try:
            from app.services.integrations.jira_service import JiraService

            jira = JiraService()

            # Get credentials from tool config or user's integration
            credentials = tool_config.get("credentials", {})

            result = await jira.create_issue(
                credentials=credentials,
                project_key=arguments.get("project_key", tool_config.get("default_project")),
                summary=arguments.get("summary", "New ticket from call"),
                description=arguments.get("description", ""),
                issue_type=arguments.get("issue_type", "Task"),
                priority=arguments.get("priority"),
                labels=arguments.get("labels", []),
                custom_fields=arguments.get("custom_fields", {})
            )

            return {
                "success": True,
                "ticket_id": result.get("key"),
                "ticket_url": result.get("self"),
                "message": f"Created ticket {result.get('key')}"
            }

        except Exception as e:
            logger.error(f"[REALTIME-TOOL] Error creating ticket: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_send_notification(
        self,
        tool_config: Dict,
        arguments: Dict,
        context: Optional[Dict]
    ) -> Dict[str, Any]:
        """Send a notification (Slack, email, etc.)"""
        notification_type = tool_config.get("notification_type", "slack")

        if notification_type == "slack":
            webhook_url = tool_config.get("webhook_url")
            if not webhook_url:
                return {"success": False, "error": "Slack webhook URL not configured"}

            message = arguments.get("message", "Notification from call")
            channel = arguments.get("channel")

            payload = {"text": message}
            if channel:
                payload["channel"] = channel

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(webhook_url, json=payload) as response:
                        return {
                            "success": response.status == 200,
                            "message": "Notification sent" if response.status == 200 else "Failed to send"
                        }
            except Exception as e:
                return {"success": False, "error": str(e)}

        elif notification_type == "email":
            # Email notification via existing email service
            try:
                from app.services.integrations.email_service import EmailService

                email_service = EmailService()
                await email_service.send_email(
                    to=arguments.get("to"),
                    subject=arguments.get("subject", "Notification"),
                    body=arguments.get("body", arguments.get("message", "")),
                    credentials=tool_config.get("credentials", {})
                )
                return {"success": True, "message": "Email sent"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": False, "error": f"Unknown notification type: {notification_type}"}

    async def _execute_calendar_check(
        self,
        tool_config: Dict,
        arguments: Dict,
        context: Optional[Dict]
    ) -> Dict[str, Any]:
        """Check calendar availability"""
        try:
            from app.services.google_calendar import CalendarService

            calendar = CalendarService()

            # Get user's calendar account IDs
            account_ids = tool_config.get("calendar_account_ids", [])
            date = arguments.get("date")
            time_slot = arguments.get("time")
            duration = arguments.get("duration", 30)

            if not account_ids:
                return {"success": False, "error": "No calendar accounts configured"}

            # Check availability
            is_available = await calendar.check_slot_availability(
                account_ids=account_ids,
                date=date,
                time=time_slot,
                duration_minutes=duration
            )

            if is_available:
                return {
                    "success": True,
                    "available": True,
                    "message": f"The time slot {date} at {time_slot} is available"
                }
            else:
                # Get alternative slots
                alternatives = await calendar.get_available_slots(
                    account_ids=account_ids,
                    date=date,
                    duration_minutes=duration,
                    num_slots=3
                )
                return {
                    "success": True,
                    "available": False,
                    "message": f"The requested slot is not available",
                    "alternatives": alternatives
                }

        except Exception as e:
            logger.error(f"[REALTIME-TOOL] Calendar check error: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_custom_function(
        self,
        tool_config: Dict,
        arguments: Dict,
        context: Optional[Dict]
    ) -> Dict[str, Any]:
        """Execute a custom function defined in the tool config"""
        # For now, custom functions without a webhook URL just return the arguments
        # This can be extended to support custom logic
        return {
            "success": True,
            "message": "Function executed",
            "received_arguments": arguments
        }

    def _render_template(self, template: Any, data: Dict) -> Any:
        """Render template with data, handling nested structures"""
        if isinstance(template, str):
            result = template
            for key, value in data.items():
                placeholder = f"{{{{{key}}}}}"
                if placeholder in result:
                    result = result.replace(placeholder, str(value) if value else "")
            return result
        elif isinstance(template, dict):
            return {k: self._render_template(v, data) for k, v in template.items()}
        elif isinstance(template, list):
            return [self._render_template(item, data) for item in template]
        return template

    def get_execution_log(self) -> List[Dict]:
        """Get the log of all tool executions during this call"""
        return self.tool_execution_log


# Default tool definitions that can be used by any assistant
DEFAULT_TOOLS = [
    {
        "name": "get_customer_info",
        "type": "database_query",
        "description": "Look up customer information by phone number or email",
        "parameters": {
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "description": "Customer phone number"
                },
                "email": {
                    "type": "string",
                    "description": "Customer email address"
                }
            }
        },
        "collection": "customers"
    },
    {
        "name": "check_appointment_availability",
        "type": "calendar_check",
        "description": "Check if a specific date and time is available for an appointment",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format"
                },
                "time": {
                    "type": "string",
                    "description": "Time in HH:MM format (24-hour)"
                },
                "duration": {
                    "type": "integer",
                    "description": "Duration in minutes",
                    "default": 30
                }
            },
            "required": ["date", "time"]
        }
    },
    {
        "name": "create_support_ticket",
        "type": "create_ticket",
        "description": "Create a support ticket for the customer's issue",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Brief summary of the issue"
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of the issue"
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "urgent"],
                    "description": "Priority level"
                }
            },
            "required": ["summary"]
        }
    }
]

"""
Workflow Execution Engine
Orchestrates workflow execution with conditions, actions, and error handling
"""
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging
from bson import ObjectId

from app.config.database import Database
from app.models.workflow import (
    Workflow, WorkflowExecution, WorkflowExecutionStatus,
    ActionExecution, ActionType, TriggerEvent, GraphData, WorkflowNode, WorkflowEdge
)
from app.models.integration import Integration, IntegrationType, IntegrationLog
from app.services.integrations.condition_evaluator import ConditionEvaluator
from app.services.integrations.jira_service import JiraService
from app.services.integrations.hubspot_service import HubSpotService
from app.services.integrations.email_service import EmailService
from app.services.integrations.credentials_encryption import credentials_encryption
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """Main workflow execution engine"""

    def __init__(self):
        self.db = Database.get_db()

    def get_integration_service(self, integration: Integration):
        """Get appropriate service instance for an integration"""
        if integration.type == IntegrationType.JIRA:
            from app.models.integration import JiraCredentials
            creds = JiraCredentials(**integration.credentials)
            return JiraService(creds)

        elif integration.type == IntegrationType.HUBSPOT:
            from app.models.integration import HubSpotCredentials
            creds = HubSpotCredentials(**integration.credentials)
            return HubSpotService(creds)

        elif integration.type == IntegrationType.EMAIL:
            from app.models.integration import EmailCredentials
            creds = EmailCredentials(**integration.credentials)
            return EmailService(creds)

        else:
            raise ValueError(f"Unsupported integration type: {integration.type}")

    async def trigger_workflow(
        self,
        trigger_event: TriggerEvent,
        trigger_data: Dict[str, Any],
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        Trigger workflows for a specific event

        Args:
            trigger_event: Event type that triggered the workflow
            trigger_data: Data associated with the event
            user_id: User ID who owns the workflows

        Returns:
            List of execution results
        """
        try:
            # Find all active workflows for this user and event
            workflows = list(
                self.db.workflows.find({
                    "user_id": user_id,
                    "trigger_event": trigger_event.value,
                    "is_active": True
                }).sort("priority", -1)  # Higher priority first
            )

            logger.info(
                f"Found {len(workflows)} workflows for event {trigger_event} "
                f"and user {user_id}"
            )

            results = []

            for workflow_doc in workflows:
                try:
                    workflow = Workflow(**workflow_doc)
                    result = await self.execute_workflow(workflow, trigger_data)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error executing workflow {workflow_doc.get('_id')}: {e}")
                    results.append({
                        "workflow_id": str(workflow_doc.get("_id")),
                        "success": False,
                        "error": str(e)
                    })

            return results

        except Exception as e:
            logger.error(f"Error triggering workflows: {e}")
            return []

    async def trigger_workflows(
        self,
        trigger_event: TriggerEvent,
        trigger_data: Dict[str, Any],
        user_id: str,
        assistant_id: Optional[str] = None,
        assigned_workflow_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Trigger workflows for a specific event with optional assistant filtering.

        This method supports filtering workflows by:
        1. Assistant's assigned_workflows list (if assistant_id provided)
        2. Explicit workflow IDs (if assigned_workflow_ids provided)
        3. All user workflows (if neither provided)

        Args:
            trigger_event: Event type that triggered the workflow
            trigger_data: Data associated with the event
            user_id: User ID who owns the workflows
            assistant_id: Optional assistant ID to filter by assigned workflows
            assigned_workflow_ids: Optional explicit list of workflow IDs to execute

        Returns:
            List of execution results
        """
        try:
            logger.info(f"[WORKFLOWS] Triggering workflows for event={trigger_event.value}, user={user_id}, assistant={assistant_id}")

            # Determine which workflows to execute
            workflow_ids_to_execute = None

            # If assistant_id provided, get its assigned workflows
            if assistant_id and not assigned_workflow_ids:
                try:
                    assistant_obj_id = ObjectId(assistant_id)
                    assistant = self.db.assistants.find_one({"_id": assistant_obj_id})
                    if assistant:
                        assigned_workflow_ids = assistant.get("assigned_workflows", [])
                        workflow_trigger_events = assistant.get("workflow_trigger_events", ["CALL_COMPLETED"])

                        # Check if this trigger event is enabled for this assistant
                        if trigger_event.value not in workflow_trigger_events:
                            logger.info(f"[WORKFLOWS] Trigger event {trigger_event.value} not enabled for assistant {assistant_id}")
                            return []

                        logger.info(f"[WORKFLOWS] Assistant {assistant_id} has {len(assigned_workflow_ids)} assigned workflows")
                except Exception as e:
                    logger.warning(f"[WORKFLOWS] Error getting assistant workflows: {e}")

            # Convert workflow IDs to ObjectIds if provided
            if assigned_workflow_ids:
                workflow_ids_to_execute = []
                for wf_id in assigned_workflow_ids:
                    try:
                        workflow_ids_to_execute.append(ObjectId(wf_id))
                    except Exception:
                        logger.warning(f"[WORKFLOWS] Invalid workflow ID: {wf_id}")

            # Build query
            query = {
                "user_id": user_id,
                "trigger_event": trigger_event.value,
                "is_active": True
            }

            # Add workflow ID filter if we have specific workflows
            if workflow_ids_to_execute:
                query["_id"] = {"$in": workflow_ids_to_execute}
                logger.info(f"[WORKFLOWS] Filtering to {len(workflow_ids_to_execute)} specific workflows")

            # Find workflows
            workflows = list(
                self.db.workflows.find(query).sort("priority", -1)
            )

            logger.info(f"[WORKFLOWS] Found {len(workflows)} workflows to execute for event {trigger_event.value}")

            if not workflows:
                logger.info(f"[WORKFLOWS] No active workflows found for user {user_id}, event {trigger_event.value}")
                return []

            # Execute workflows
            results = []
            for workflow_doc in workflows:
                workflow_id = str(workflow_doc.get("_id"))
                workflow_name = workflow_doc.get("name", "Unnamed")

                try:
                    logger.info(f"[WORKFLOWS] Executing workflow: {workflow_name} (ID: {workflow_id})")

                    # Check if it's a graph-based or n8n workflow
                    graph_data = workflow_doc.get("graph_data")
                    n8n_workflow_id = workflow_doc.get("n8n_workflow_id")
                    webhook_url = workflow_doc.get("webhook_url")

                    if n8n_workflow_id or webhook_url:
                        # This is an n8n/webhook workflow - trigger via webhook
                        result = await self._execute_webhook_workflow(workflow_doc, trigger_data)
                    elif graph_data and graph_data.get("nodes"):
                        # Graph-based workflow
                        workflow = Workflow(**workflow_doc)
                        result = await self.execute_graph_workflow(workflow, trigger_data)
                    else:
                        # Legacy linear workflow
                        workflow = Workflow(**workflow_doc)
                        result = await self.execute_workflow(workflow, trigger_data)

                    results.append({
                        "workflow_id": workflow_id,
                        "workflow_name": workflow_name,
                        **result
                    })

                    logger.info(f"[WORKFLOWS] Workflow {workflow_name} completed: success={result.get('success', False)}")

                except Exception as e:
                    logger.error(f"[WORKFLOWS] Error executing workflow {workflow_id}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    results.append({
                        "workflow_id": workflow_id,
                        "workflow_name": workflow_name,
                        "success": False,
                        "error": str(e)
                    })

            # Log summary
            success_count = sum(1 for r in results if r.get("success"))
            logger.info(f"[WORKFLOWS] Completed {success_count}/{len(results)} workflows successfully")

            return results

        except Exception as e:
            logger.error(f"[WORKFLOWS] Error triggering workflows: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    async def _execute_webhook_workflow(
        self,
        workflow_doc: Dict[str, Any],
        trigger_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a webhook-based workflow (n8n or custom webhook).

        Args:
            workflow_doc: Workflow document from database
            trigger_data: Data to send to the webhook

        Returns:
            Execution result
        """
        import aiohttp
        import time

        start_time = time.time()
        workflow_id = str(workflow_doc.get("_id"))
        workflow_name = workflow_doc.get("name", "Unnamed")

        try:
            # Get webhook URL
            webhook_url = workflow_doc.get("webhook_url")
            n8n_workflow_id = workflow_doc.get("n8n_workflow_id")

            if not webhook_url:
                # Try to construct n8n webhook URL
                n8n_base_url = workflow_doc.get("n8n_base_url") or "https://n8n.convis.ai"
                if n8n_workflow_id:
                    webhook_url = f"{n8n_base_url}/webhook/{n8n_workflow_id}"

            if not webhook_url:
                return {
                    "success": False,
                    "error": "No webhook URL configured for workflow"
                }

            logger.info(f"[WORKFLOWS] Triggering webhook: {webhook_url}")

            # Prepare payload with all call data
            payload = {
                "event": trigger_data.get("trigger_event", "call_completed"),
                "timestamp": trigger_data.get("timestamp"),
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
                # Call data
                "call": trigger_data.get("call", {}),
                "call_id": trigger_data.get("call_id"),
                "call_sid": trigger_data.get("call", {}).get("id") or trigger_data.get("call_id"),
                "duration": trigger_data.get("call", {}).get("duration", 0),
                "direction": trigger_data.get("call", {}).get("direction"),
                "from_number": trigger_data.get("call", {}).get("from_number"),
                "to_number": trigger_data.get("call", {}).get("to_number"),
                "recording_url": trigger_data.get("call", {}).get("recording_url"),
                # Transcript and analysis
                "transcription": trigger_data.get("call", {}).get("transcription", ""),
                "transcript": trigger_data.get("call", {}).get("transcription", ""),
                "summary": trigger_data.get("call", {}).get("summary", ""),
                "sentiment": trigger_data.get("sentiment") or trigger_data.get("call", {}).get("sentiment"),
                "sentiment_score": trigger_data.get("call", {}).get("sentiment_score", 0.0),
                # Customer data
                "customer": trigger_data.get("customer", {}),
                "customer_name": trigger_data.get("customer_name") or trigger_data.get("customer", {}).get("name", ""),
                "customer_email": trigger_data.get("customer_email") or trigger_data.get("customer", {}).get("email", ""),
                "customer_phone": trigger_data.get("customer_phone") or trigger_data.get("customer", {}).get("phone", ""),
                "email_mentioned": trigger_data.get("email_mentioned", False),
                # Issue tracking
                "issue_description": trigger_data.get("issue_description"),
                "issue_category": trigger_data.get("issue_category"),
                "issue_priority": trigger_data.get("issue_priority"),
                "action_required": trigger_data.get("action_required"),
                "extracted_data": trigger_data.get("extracted_data", {}),
                # Appointment
                "appointment_booked": trigger_data.get("appointment_booked", False),
                "appointment_date": trigger_data.get("appointment_date"),
                # Metadata
                "campaign_id": trigger_data.get("campaign_id"),
                "assistant_id": trigger_data.get("assistant_id"),
                "metadata": trigger_data.get("metadata", {})
            }

            # Add any additional fields from trigger_data
            for key, value in trigger_data.items():
                if key not in payload:
                    payload[key] = value

            # Send webhook request
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    webhook_url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Workflow-ID": workflow_id,
                        "X-Workflow-Name": workflow_name
                    }
                ) as response:
                    response_text = await response.text()
                    duration_ms = (time.time() - start_time) * 1000

                    if response.status >= 200 and response.status < 300:
                        logger.info(f"[WORKFLOWS] Webhook triggered successfully: {response.status}")

                        # Try to parse response
                        try:
                            response_data = await response.json() if response.content_type == 'application/json' else {"raw": response_text}
                        except:
                            response_data = {"raw": response_text[:500]}

                        # Update workflow execution stats
                        self.db.workflows.update_one(
                            {"_id": workflow_doc["_id"]},
                            {
                                "$set": {
                                    "last_executed_at": datetime.utcnow(),
                                    "last_execution_status": "success",
                                    "updated_at": datetime.utcnow()
                                },
                                "$inc": {
                                    "execution_count": 1,
                                    "success_count": 1
                                }
                            }
                        )

                        return {
                            "success": True,
                            "status_code": response.status,
                            "response": response_data,
                            "duration_ms": duration_ms
                        }
                    else:
                        logger.error(f"[WORKFLOWS] Webhook failed: {response.status} - {response_text[:200]}")

                        # Update workflow with failure
                        self.db.workflows.update_one(
                            {"_id": workflow_doc["_id"]},
                            {
                                "$set": {
                                    "last_executed_at": datetime.utcnow(),
                                    "last_execution_status": "failed",
                                    "last_execution_error": response_text[:500],
                                    "updated_at": datetime.utcnow()
                                },
                                "$inc": {
                                    "execution_count": 1,
                                    "failure_count": 1
                                }
                            }
                        )

                        return {
                            "success": False,
                            "status_code": response.status,
                            "error": f"Webhook returned {response.status}: {response_text[:200]}",
                            "duration_ms": duration_ms
                        }

        except aiohttp.ClientError as e:
            logger.error(f"[WORKFLOWS] Webhook connection error: {e}")
            return {
                "success": False,
                "error": f"Connection error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"[WORKFLOWS] Webhook execution error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }

    async def execute_workflow(
        self,
        workflow: Workflow,
        trigger_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a single workflow

        Args:
            workflow: Workflow to execute (can be Workflow model or dict)
            trigger_data: Event data

        Returns:
            Execution result
        """
        # Check if this is a graph-based workflow
        graph_data = None
        if isinstance(workflow, dict):
            graph_data = workflow.get("graph_data")
        elif hasattr(workflow, 'graph_data'):
            graph_data = workflow.graph_data

        # If graph_data exists and has nodes, use graph execution
        if graph_data:
            if isinstance(graph_data, dict) and graph_data.get("nodes"):
                # Convert dict to Workflow model if needed
                if isinstance(workflow, dict):
                    workflow = Workflow(**workflow)
                return await self.execute_graph_workflow(workflow, trigger_data)
            elif hasattr(graph_data, 'nodes') and graph_data.nodes:
                return await self.execute_graph_workflow(workflow, trigger_data)

        # Otherwise use legacy linear execution
        start_time = time.time()
        execution_id = str(ObjectId())

        # Handle both dict and Workflow model
        if isinstance(workflow, dict):
            workflow_id = str(workflow.get("_id") or workflow.get("id", "unknown"))
            workflow_name = workflow.get("name", "Unnamed Workflow")
            workflow_user_id = workflow.get("user_id")
            workflow_trigger_event = workflow.get("trigger_event")
            workflow_conditions = workflow.get("conditions", [])
            workflow_actions = workflow.get("actions", [])
        else:
            workflow_id = str(workflow.id) if hasattr(workflow, 'id') else str(workflow._id) if hasattr(workflow, '_id') else "unknown"
            workflow_name = workflow.name
            workflow_user_id = workflow.user_id
            workflow_trigger_event = workflow.trigger_event
            workflow_conditions = workflow.conditions or []
            workflow_actions = workflow.actions or []

        logger.info(f"Executing workflow: {workflow_name} (ID: {workflow_id})")

        # Create execution record
        execution = WorkflowExecution(
            _id=execution_id,
            workflow_id=workflow_id,
            user_id=workflow_user_id,
            trigger_event=workflow_trigger_event,
            trigger_data=trigger_data,
            status=WorkflowExecutionStatus.RUNNING,
            call_id=trigger_data.get("call_id"),
            campaign_id=trigger_data.get("campaign_id")
        )

        try:
            # Evaluate conditions
            conditions_met = True
            if workflow_conditions:
                conditions_met = ConditionEvaluator.evaluate_conditions_advanced(
                    workflow_conditions,
                    trigger_data
                )
                execution.conditions_met = conditions_met

                logger.info(f"Workflow conditions met: {conditions_met}")

            if not conditions_met:
                # Conditions not met, skip execution
                execution.status = WorkflowExecutionStatus.COMPLETED
                execution.completed_at = datetime.utcnow()
                execution.duration_ms = (time.time() - start_time) * 1000

                # Save execution
                self.db.workflow_executions.insert_one(execution.dict(by_alias=True))

                return {
                    "success": True,
                    "execution_id": execution_id,
                    "workflow_id": workflow_id,
                    "conditions_met": False,
                    "message": "Workflow conditions not met, skipped execution"
                }

            # Execute actions (with delay support)
            action_results = []
            for idx, action in enumerate(workflow_actions):
                try:
                    # Handle action as dict or model
                    if isinstance(action, dict):
                        action_type = action.get("type")
                        action_config = action.get("config", {})
                        action_condition = action.get("condition")
                        action_on_error = action.get("on_error", "continue")
                        action_integration_id = action.get("integration_id")
                        action_delay_seconds = action.get("delay_seconds")
                        action_delay_until = action.get("delay_until")
                    else:
                        action_type = action.type
                        action_config = action.config
                        action_condition = action.condition if hasattr(action, 'condition') else None
                        action_on_error = action.on_error if hasattr(action, 'on_error') else "continue"
                        action_integration_id = action.integration_id if hasattr(action, 'integration_id') else None
                        action_delay_seconds = action.delay_seconds if hasattr(action, 'delay_seconds') else None
                        action_delay_until = action.delay_until if hasattr(action, 'delay_until') else None

                    # Check action-level conditions
                    if action_condition:
                        action_conditions_met = ConditionEvaluator.evaluate_conditions_advanced(
                            action_condition,
                            trigger_data
                        )
                        if not action_conditions_met:
                            logger.info(f"Action {action_type} conditions not met, skipping")
                            continue

                    # Handle DELAY action type
                    if action_type == "delay" or action_type == ActionType.DELAY:
                        from app.services.integrations.celery_tasks import continue_workflow_after_delay

                        delay_seconds = action_delay_seconds or action_config.get("delay_seconds", 60)

                        # Get remaining actions after this delay
                        remaining_actions = workflow_actions[idx + 1:]

                        if remaining_actions:
                            logger.info(f"Scheduling workflow continuation after {delay_seconds} seconds")

                            # Schedule remaining actions
                            continue_workflow_after_delay.apply_async(
                                args=[
                                    workflow_id,
                                    [a.dict() if hasattr(a, 'dict') else a for a in remaining_actions],
                                    trigger_data,
                                    workflow_user_id,
                                    execution_id
                                ],
                                countdown=delay_seconds
                            )

                            # Mark execution as pending (will be updated by celery task)
                            execution.status = WorkflowExecutionStatus.PENDING
                            action_results.append({
                                "action_id": action.get("id") if isinstance(action, dict) else getattr(action, "id", ""),
                                "action_type": "delay",
                                "status": "scheduled",
                                "started_at": datetime.utcnow(),
                                "completed_at": datetime.utcnow(),
                                "duration_ms": 0,
                                "output_data": {"delay_seconds": delay_seconds, "remaining_actions": len(remaining_actions)},
                                "success": True
                            })

                            # Break here as remaining actions will be executed by celery
                            break
                        else:
                            # No remaining actions, just wait
                            logger.info(f"Delay action is last in workflow, no remaining actions")
                            action_results.append({
                                "action_id": action.get("id") if isinstance(action, dict) else getattr(action, "id", ""),
                                "action_type": "delay",
                                "status": "completed",
                                "started_at": datetime.utcnow(),
                                "completed_at": datetime.utcnow(),
                                "duration_ms": 0,
                                "output_data": {"delay_seconds": delay_seconds},
                                "success": True
                            })
                            continue

                    # Handle BRANCH action type (conditional if-else)
                    if action_type == "branch" or action_type == ActionType.BRANCH:
                        # Get branch fields
                        if isinstance(action, dict):
                            branch_conditions = action.get("branch_conditions")
                            if_actions = action.get("if_actions", [])
                            else_actions = action.get("else_actions", [])
                        else:
                            branch_conditions = action.branch_conditions if hasattr(action, 'branch_conditions') else None
                            if_actions = action.if_actions if hasattr(action, 'if_actions') else []
                            else_actions = action.else_actions if hasattr(action, 'else_actions') else []

                        # Evaluate branch conditions
                        branch_result = True
                        if branch_conditions:
                            branch_result = ConditionEvaluator.evaluate_conditions_advanced(
                                branch_conditions,
                                trigger_data
                            )

                        # Choose which actions to execute
                        selected_branch = "if" if branch_result else "else"
                        branch_actions = if_actions if branch_result else else_actions

                        logger.info(f"Branch evaluated: taking '{selected_branch}' path with {len(branch_actions)} actions")

                        # Execute branch actions
                        branch_action_results = []
                        for branch_action in branch_actions:
                            try:
                                branch_action_result = await self.execute_action(
                                    branch_action,
                                    trigger_data,
                                    workflow_user_id
                                )
                                branch_action_results.append(branch_action_result)

                                # Stop if branch action failed and error handling is "stop"
                                branch_on_error = branch_action.get("on_error", "continue") if isinstance(branch_action, dict) else getattr(branch_action, "on_error", "continue")
                                if not branch_action_result.get("success") and branch_on_error == "stop":
                                    break

                            except Exception as e:
                                logger.error(f"Error executing branch action: {e}")
                                branch_action_results.append({
                                    "success": False,
                                    "error": str(e)
                                })
                                break

                        # Record branch execution
                        action_results.append({
                            "action_id": action.get("id") if isinstance(action, dict) else getattr(action, "id", ""),
                            "action_type": "branch",
                            "status": "completed",
                            "started_at": datetime.utcnow(),
                            "completed_at": datetime.utcnow(),
                            "duration_ms": 0,
                            "output_data": {
                                "branch_taken": selected_branch,
                                "condition_result": branch_result,
                                "actions_executed": len(branch_action_results),
                                "actions_succeeded": sum(1 for r in branch_action_results if r.get("success"))
                            },
                            "success": True
                        })

                        # Add branch action results to main results
                        action_results.extend(branch_action_results)
                        continue

                    # Handle LOOP action type (for-each iteration)
                    if action_type == "loop" or action_type == ActionType.LOOP:
                        # Get loop fields
                        if isinstance(action, dict):
                            loop_array_field = action.get("loop_array_field")
                            loop_item_variable = action.get("loop_item_variable", "item")
                            loop_index_variable = action.get("loop_index_variable", "index")
                            loop_actions = action.get("loop_actions", [])
                            loop_max_iterations = action.get("loop_max_iterations", 100)
                        else:
                            loop_array_field = action.loop_array_field if hasattr(action, 'loop_array_field') else None
                            loop_item_variable = action.loop_item_variable if hasattr(action, 'loop_item_variable') else "item"
                            loop_index_variable = action.loop_index_variable if hasattr(action, 'loop_index_variable') else "index"
                            loop_actions = action.loop_actions if hasattr(action, 'loop_actions') else []
                            loop_max_iterations = action.loop_max_iterations if hasattr(action, 'loop_max_iterations') else 100

                        # Get array to iterate over
                        array_data = trigger_data.get(loop_array_field, [])
                        if not isinstance(array_data, list):
                            logger.warning(f"Loop field '{loop_array_field}' is not an array, skipping loop")
                            action_results.append({
                                "action_id": action.get("id") if isinstance(action, dict) else getattr(action, "id", ""),
                                "action_type": "loop",
                                "status": "skipped",
                                "started_at": datetime.utcnow(),
                                "completed_at": datetime.utcnow(),
                                "duration_ms": 0,
                                "error_message": f"Field '{loop_array_field}' is not an array",
                                "success": False
                            })
                            continue

                        # Limit iterations
                        iteration_count = min(len(array_data), loop_max_iterations)
                        logger.info(f"Starting loop over {iteration_count} items (field: {loop_array_field})")

                        # Execute actions for each item
                        loop_action_results = []
                        for idx, item in enumerate(array_data[:iteration_count]):
                            # Add loop variables to context
                            loop_context = {
                                **trigger_data,
                                loop_item_variable: item,
                                loop_index_variable: idx,
                                "loop_count": iteration_count,
                                "loop_is_first": idx == 0,
                                "loop_is_last": idx == iteration_count - 1
                            }

                            # Execute loop actions with item context
                            for loop_action in loop_actions:
                                try:
                                    loop_action_result = await self.execute_action(
                                        loop_action,
                                        loop_context,
                                        workflow_user_id
                                    )
                                    loop_action_results.append({
                                        **loop_action_result,
                                        "loop_iteration": idx,
                                        "loop_item": item
                                    })

                                    # Stop if loop action failed and error handling is "stop"
                                    loop_on_error = loop_action.get("on_error", "continue") if isinstance(loop_action, dict) else getattr(loop_action, "on_error", "continue")
                                    if not loop_action_result.get("success") and loop_on_error == "stop":
                                        logger.warning(f"Loop action failed at iteration {idx}, stopping loop")
                                        break

                                except Exception as e:
                                    logger.error(f"Error executing loop action at iteration {idx}: {e}")
                                    loop_action_results.append({
                                        "success": False,
                                        "error": str(e),
                                        "loop_iteration": idx,
                                        "loop_item": item
                                    })
                                    break

                        # Record loop execution
                        action_results.append({
                            "action_id": action.get("id") if isinstance(action, dict) else getattr(action, "id", ""),
                            "action_type": "loop",
                            "status": "completed",
                            "started_at": datetime.utcnow(),
                            "completed_at": datetime.utcnow(),
                            "duration_ms": 0,
                            "output_data": {
                                "iterations_completed": iteration_count,
                                "actions_per_iteration": len(loop_actions),
                                "total_actions_executed": len(loop_action_results),
                                "actions_succeeded": sum(1 for r in loop_action_results if r.get("success"))
                            },
                            "success": True
                        })

                        # Add loop action results to main results
                        action_results.extend(loop_action_results)
                        continue

                    # Execute action immediately
                    action_result = await self.execute_action(
                        action,
                        trigger_data,
                        workflow_user_id
                    )
                    action_results.append(action_result)

                    # Handle errors
                    if not action_result.get("success", False):
                        if action_on_error == "stop":
                            logger.error(f"Action failed, stopping workflow: {action_result.get('error')}")
                            break
                        elif action_on_error == "continue":
                            logger.warning(f"Action failed, continuing: {action_result.get('error')}")
                            continue

                except Exception as e:
                    logger.error(f"Error executing action {action_type}: {e}")
                    action_result = {
                        "action_type": action_type,
                        "success": False,
                        "error": str(e)
                    }
                    action_results.append(action_result)

                    if action_on_error == "stop":
                        break

            # Determine overall status
            execution.actions_executed = [
                ActionExecution(**result) for result in action_results
                if "action_type" in result
            ]

            success_count = sum(1 for r in action_results if r.get("success", False))
            total_count = len(action_results)

            if success_count == total_count:
                execution.status = WorkflowExecutionStatus.COMPLETED
            elif success_count > 0:
                execution.status = WorkflowExecutionStatus.PARTIAL_SUCCESS
            else:
                execution.status = WorkflowExecutionStatus.FAILED

            execution.completed_at = datetime.utcnow()
            execution.duration_ms = (time.time() - start_time) * 1000

            # Save execution
            self.db.workflow_executions.insert_one(execution.dict(by_alias=True))

            # Update workflow statistics
            # Convert workflow_id to ObjectId if it's a string
            from bson import ObjectId as BsonObjectId
            try:
                wf_id = BsonObjectId(workflow_id) if isinstance(workflow_id, str) else workflow_id
            except:
                wf_id = workflow_id

            self.db.workflows.update_one(
                {"_id": wf_id},
                {
                    "$set": {
                        "last_executed_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    },
                    "$inc": {
                        "execution_count": 1,
                        "success_count": 1 if execution.status == WorkflowExecutionStatus.COMPLETED else 0,
                        "failure_count": 1 if execution.status == WorkflowExecutionStatus.FAILED else 0
                    }
                }
            )

            logger.info(
                f"Workflow execution completed: {execution.status} "
                f"({success_count}/{total_count} actions succeeded)"
            )

            # Create notification based on execution result
            try:
                notification_service = NotificationService(self.db)

                if execution.status == WorkflowExecutionStatus.COMPLETED:
                    # Workflow completed successfully
                    await notification_service.notify_workflow_success(
                        user_id=workflow_user_id,
                        workflow_id=workflow_id,
                        workflow_name=workflow_name,
                        execution_id=execution_id
                    )
                elif execution.status == WorkflowExecutionStatus.FAILED:
                    # Workflow failed
                    error_msg = execution.error_message or "Unknown error"
                    await notification_service.notify_workflow_failed(
                        user_id=workflow_user_id,
                        workflow_id=workflow_id,
                        workflow_name=workflow_name,
                        execution_id=execution_id,
                        error_message=error_msg
                    )
                elif execution.status == WorkflowExecutionStatus.PARTIAL_SUCCESS:
                    # Some actions failed
                    failed_actions = [r for r in action_results if not r.get("success", False)]
                    if failed_actions:
                        first_failed = failed_actions[0]
                        await notification_service.notify_workflow_action_failed(
                            user_id=workflow_user_id,
                            workflow_id=workflow_id,
                            workflow_name=workflow_name,
                            action_name=first_failed.get("action_type", "Unknown"),
                            error_message=first_failed.get("error_message", "Unknown error")
                        )
            except Exception as notify_error:
                logger.error(f"Failed to create workflow notification: {notify_error}")
                # Don't fail the workflow if notification fails

            return {
                "success": execution.status in [
                    WorkflowExecutionStatus.COMPLETED,
                    WorkflowExecutionStatus.PARTIAL_SUCCESS
                ],
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
                "status": execution.status,
                "conditions_met": conditions_met,
                "actions_executed": total_count,
                "actions_succeeded": success_count,
                "duration_ms": execution.duration_ms
            }

        except Exception as e:
            logger.error(f"Workflow execution error: {e}")
            execution.status = WorkflowExecutionStatus.FAILED
            execution.error_message = str(e)
            execution.completed_at = datetime.utcnow()
            execution.duration_ms = (time.time() - start_time) * 1000

            # Save execution
            self.db.workflow_executions.insert_one(execution.dict(by_alias=True))

            # Create failure notification
            try:
                notification_service = NotificationService(self.db)
                await notification_service.notify_workflow_failed(
                    user_id=workflow_user_id,
                    workflow_id=workflow_id,
                    workflow_name=workflow_name,
                    execution_id=execution_id,
                    error_message=str(e)
                )
            except Exception as notify_error:
                logger.error(f"Failed to create workflow failure notification: {notify_error}")

            return {
                "success": False,
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "error": str(e)
            }

    async def execute_action(
        self,
        action: Any,
        context_data: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """
        Execute a single workflow action

        Args:
            action: Action to execute (can be dict or model)
            context_data: Context data for template rendering
            user_id: User ID

        Returns:
            Action execution result
        """
        start_time = time.time()
        action_start = datetime.utcnow()

        # Handle both dict and model
        if isinstance(action, dict):
            action_id = action.get("id") or action.get("_id", "")
            action_type = action.get("type")
            action_config = action.get("config", {})
            action_integration_id = action.get("integration_id")
        else:
            action_id = action.id if hasattr(action, 'id') else ""
            action_type = action.type
            action_config = action.config
            action_integration_id = action.integration_id if hasattr(action, 'integration_id') else None

        # Convert action_type string to ActionType enum if needed
        if isinstance(action_type, str):
            try:
                action_type_enum = ActionType(action_type)
            except ValueError:
                # Map string to enum
                action_type_map = {
                    "create_jira_ticket": ActionType.CREATE_JIRA_TICKET,
                    "update_jira_ticket": ActionType.UPDATE_JIRA_TICKET,
                    "create_hubspot_contact": ActionType.CREATE_HUBSPOT_CONTACT,
                    "update_hubspot_contact": ActionType.UPDATE_HUBSPOT_CONTACT,
                    "create_hubspot_note": ActionType.CREATE_HUBSPOT_NOTE,
                    "send_email": ActionType.SEND_EMAIL,
                }
                action_type_enum = action_type_map.get(action_type)
                if not action_type_enum:
                    raise ValueError(f"Unknown action type: {action_type}")
        else:
            action_type_enum = action_type

        try:
            # Get integration if needed
            integration = None
            service = None

            if action_integration_id:
                # Convert string ID to ObjectId for MongoDB query
                try:
                    obj_id = ObjectId(action_integration_id)
                except Exception:
                    raise ValueError(f"Invalid integration ID format: {action_integration_id}")

                integration_doc = self.db.integrations.find_one({
                    "_id": obj_id,
                    "user_id": user_id,
                    "is_active": True
                })

                if not integration_doc:
                    raise ValueError(f"Integration {action_integration_id} not found or inactive")

                # Decrypt credentials before creating the Integration model
                decrypted_credentials = credentials_encryption.decrypt_credentials(
                    integration_doc["credentials"],
                    user_id
                )

                # Convert _id to string for Pydantic model
                integration_data = {**integration_doc}
                integration_data["_id"] = str(integration_data["_id"])
                integration_data["credentials"] = decrypted_credentials

                integration = Integration(**integration_data)
                service = self.get_integration_service(integration)

            # Execute based on action type
            result = None

            if action_type_enum == ActionType.CREATE_JIRA_TICKET:
                if not service:
                    raise ValueError("Jira integration required")
                result = service.create_issue(action_config, context_data)

            elif action_type_enum == ActionType.UPDATE_JIRA_TICKET:
                if not service:
                    raise ValueError("Jira integration required")
                issue_key = action_config.get("issue_key")
                result = service.update_issue(issue_key, action_config, context_data)

            elif action_type_enum == ActionType.CREATE_HUBSPOT_CONTACT:
                if not service:
                    raise ValueError("HubSpot integration required")
                result = service.create_contact(action_config, context_data)

            elif action_type_enum == ActionType.UPDATE_HUBSPOT_CONTACT:
                if not service:
                    raise ValueError("HubSpot integration required")
                contact_id = action_config.get("contact_id")
                result = service.update_contact(contact_id, action_config, context_data)

            elif action_type_enum == ActionType.CREATE_HUBSPOT_NOTE:
                if not service:
                    raise ValueError("HubSpot integration required")
                result = service.create_note(action_config, context_data)

            elif action_type_enum == ActionType.SEND_EMAIL:
                if not service:
                    raise ValueError("Email integration required")
                result = service.send_email(action_config, context_data)

            elif action_type_enum == ActionType.SEND_SLACK_MESSAGE:
                # Send Slack message via webhook
                import aiohttp
                webhook_url = action_config.get("webhook_url", "")
                if not webhook_url:
                    raise ValueError("Slack webhook URL required")

                message = self._render_template(action_config.get("message", ""), context_data)
                channel = action_config.get("channel", "")

                payload = {"text": message}
                if channel:
                    payload["channel"] = channel

                async with aiohttp.ClientSession() as session:
                    async with session.post(webhook_url, json=payload) as response:
                        result = {
                            "success": response.status == 200,
                            "status_code": response.status,
                            "message": "Slack message sent" if response.status == 200 else "Failed to send Slack message"
                        }

            elif action_type_enum == ActionType.CALL_WEBHOOK:
                # Make HTTP request to external URL
                import aiohttp
                url = self._render_template(action_config.get("url", ""), context_data)
                if not url:
                    raise ValueError("Webhook URL required")

                method = action_config.get("method", "POST").upper()
                headers = action_config.get("headers", {})
                body = action_config.get("body", {})

                # Render body templates
                rendered_body = {}
                for key, value in body.items():
                    if isinstance(value, str):
                        rendered_body[key] = self._render_template(value, context_data)
                    else:
                        rendered_body[key] = value

                timeout = aiohttp.ClientTimeout(total=action_config.get("timeout_seconds", 30))
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.request(
                        method=method,
                        url=url,
                        headers=headers,
                        json=rendered_body if method in ["POST", "PUT", "PATCH"] else None,
                        params=rendered_body if method == "GET" else None
                    ) as response:
                        try:
                            response_data = await response.json() if response.content_type == 'application/json' else await response.text()
                        except:
                            response_data = await response.text()

                        result = {
                            "success": response.status < 400,
                            "status_code": response.status,
                            "response": response_data
                        }

            elif action_type_enum == ActionType.UPDATE_DATABASE:
                # Update database record
                # This supports MongoDB (internal) or external databases via integration
                collection_name = action_config.get("collection", action_config.get("table", ""))
                operation = action_config.get("operation", "update_one")
                query = action_config.get("query", {})
                data = action_config.get("data", {})

                # Render templates in query and data
                rendered_query = {}
                for key, value in query.items():
                    if isinstance(value, str):
                        rendered_query[key] = self._render_template(value, context_data)
                    else:
                        rendered_query[key] = value

                rendered_data = {}
                for key, value in data.items():
                    if isinstance(value, str):
                        rendered_data[key] = self._render_template(value, context_data)
                    else:
                        rendered_data[key] = value

                if not collection_name:
                    raise ValueError("Collection/table name required for database update")

                # Use internal MongoDB
                try:
                    collection = self.db[collection_name]

                    if operation == "insert_one":
                        insert_result = collection.insert_one(rendered_data)
                        result = {
                            "success": True,
                            "operation": "insert_one",
                            "inserted_id": str(insert_result.inserted_id)
                        }
                    elif operation == "update_one":
                        update_result = collection.update_one(rendered_query, {"$set": rendered_data})
                        result = {
                            "success": True,
                            "operation": "update_one",
                            "matched_count": update_result.matched_count,
                            "modified_count": update_result.modified_count
                        }
                    elif operation == "update_many":
                        update_result = collection.update_many(rendered_query, {"$set": rendered_data})
                        result = {
                            "success": True,
                            "operation": "update_many",
                            "matched_count": update_result.matched_count,
                            "modified_count": update_result.modified_count
                        }
                    elif operation == "delete_one":
                        delete_result = collection.delete_one(rendered_query)
                        result = {
                            "success": True,
                            "operation": "delete_one",
                            "deleted_count": delete_result.deleted_count
                        }
                    elif operation == "delete_many":
                        delete_result = collection.delete_many(rendered_query)
                        result = {
                            "success": True,
                            "operation": "delete_many",
                            "deleted_count": delete_result.deleted_count
                        }
                    else:
                        raise ValueError(f"Unsupported database operation: {operation}")

                except Exception as db_error:
                    result = {
                        "success": False,
                        "error": f"Database operation failed: {str(db_error)}"
                    }

            else:
                raise ValueError(f"Unsupported action type: {action_type_enum}")

            # Log integration action
            if integration:
                # Get string representation safely
                action_type_str = action_type_enum.value if hasattr(action_type_enum, 'value') else str(action_type_enum) if action_type_enum else str(action_type)

                log = IntegrationLog(
                    integration_id=integration.id,
                    action=action_type_str,
                    status="success" if result.get("success") else "failed",
                    request_data=action_config,
                    response_data=result,
                    error_message=result.get("error") if not result.get("success") else None,
                    duration_ms=(time.time() - start_time) * 1000
                )
                self.db.integration_logs.insert_one(log.dict(by_alias=True))

            # Build action execution result
            # Get string representation safely
            action_type_str = action_type_enum.value if hasattr(action_type_enum, 'value') else str(action_type_enum) if action_type_enum else str(action_type)

            return {
                "action_id": action_id,
                "action_type": action_type_str,
                "status": "success" if result.get("success") else "failed",
                "started_at": action_start,
                "completed_at": datetime.utcnow(),
                "duration_ms": (time.time() - start_time) * 1000,
                "input_data": action_config,
                "output_data": result,
                "error_message": result.get("error") if not result.get("success") else None,
                "success": result.get("success", False)
            }

        except Exception as e:
            logger.error(f"Action execution error: {e}")
            # Get string representation safely
            try:
                action_type_str = action_type_enum.value if hasattr(action_type_enum, 'value') else str(action_type_enum) if action_type_enum else str(action_type)
            except:
                action_type_str = str(action_type) if action_type else "unknown"

            return {
                "action_id": action_id,
                "action_type": action_type_str,
                "status": "failed",
                "started_at": action_start,
                "completed_at": datetime.utcnow(),
                "duration_ms": (time.time() - start_time) * 1000,
                "error_message": str(e),
                "success": False
            }

    # ==================== Graph-Based Workflow Execution ====================

    async def execute_graph_workflow(
        self,
        workflow: Workflow,
        trigger_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a graph-based workflow by traversing nodes and edges

        Args:
            workflow: Workflow with graph_data
            trigger_data: Event data that triggered the workflow

        Returns:
            Execution result
        """
        start_time = time.time()
        execution_id = str(ObjectId())

        workflow_id = str(workflow.id) if workflow.id else "unknown"
        workflow_name = workflow.name
        workflow_user_id = workflow.user_id

        logger.info(f"Executing graph workflow: {workflow_name} (ID: {workflow_id})")

        # Create execution record
        execution = WorkflowExecution(
            _id=execution_id,
            workflow_id=workflow_id,
            user_id=workflow_user_id,
            trigger_event=workflow.trigger_event,
            trigger_data=trigger_data,
            status=WorkflowExecutionStatus.RUNNING,
            call_id=trigger_data.get("call_id"),
            campaign_id=trigger_data.get("campaign_id")
        )

        try:
            graph_data = workflow.graph_data
            if not graph_data or not graph_data.nodes:
                raise ValueError("Workflow has no graph data or nodes")

            # Convert to dicts for easier handling
            nodes = {n.id: n for n in graph_data.nodes}
            edges = graph_data.edges

            # Build adjacency list for graph traversal
            outgoing_edges = {}  # node_id -> list of edges
            for edge in edges:
                if edge.source not in outgoing_edges:
                    outgoing_edges[edge.source] = []
                outgoing_edges[edge.source].append(edge)

            # Find trigger node (entry point)
            trigger_node = None
            for node in graph_data.nodes:
                if node.type == "trigger":
                    trigger_node = node
                    break

            if not trigger_node:
                raise ValueError("Workflow has no trigger node")

            # Execute graph starting from trigger
            action_results = []
            context = {**trigger_data}  # Mutable context that can be enriched by nodes

            # BFS traversal of the graph
            visited = set()
            queue = [trigger_node.id]

            while queue:
                current_node_id = queue.pop(0)

                if current_node_id in visited:
                    continue
                visited.add(current_node_id)

                current_node = nodes.get(current_node_id)
                if not current_node:
                    continue

                logger.info(f"Processing node: {current_node.type} ({current_node_id})")

                # Execute node based on type
                node_result = await self._execute_graph_node(
                    current_node,
                    context,
                    workflow_user_id
                )
                action_results.append(node_result)

                # Determine next nodes based on node type and result
                next_nodes = self._get_next_nodes(
                    current_node,
                    outgoing_edges.get(current_node_id, []),
                    node_result,
                    context
                )

                for next_node_id in next_nodes:
                    if next_node_id not in visited:
                        queue.append(next_node_id)

            # Determine overall status
            success_count = sum(1 for r in action_results if r.get("success", False))
            total_count = len(action_results)

            if success_count == total_count:
                execution.status = WorkflowExecutionStatus.COMPLETED
            elif success_count > 0:
                execution.status = WorkflowExecutionStatus.PARTIAL_SUCCESS
            else:
                execution.status = WorkflowExecutionStatus.FAILED

            execution.completed_at = datetime.utcnow()
            execution.duration_ms = (time.time() - start_time) * 1000

            # Save execution
            self.db.workflow_executions.insert_one(execution.dict(by_alias=True))

            # Update workflow statistics
            from bson import ObjectId as BsonObjectId
            try:
                wf_id = BsonObjectId(workflow_id) if isinstance(workflow_id, str) else workflow_id
            except:
                wf_id = workflow_id

            self.db.workflows.update_one(
                {"_id": wf_id},
                {
                    "$set": {
                        "last_executed_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    },
                    "$inc": {
                        "execution_count": 1,
                        "success_count": 1 if execution.status == WorkflowExecutionStatus.COMPLETED else 0,
                        "failure_count": 1 if execution.status == WorkflowExecutionStatus.FAILED else 0
                    }
                }
            )

            logger.info(
                f"Graph workflow execution completed: {execution.status} "
                f"({success_count}/{total_count} nodes executed successfully)"
            )

            return {
                "success": execution.status in [
                    WorkflowExecutionStatus.COMPLETED,
                    WorkflowExecutionStatus.PARTIAL_SUCCESS
                ],
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
                "status": execution.status,
                "nodes_executed": total_count,
                "nodes_succeeded": success_count,
                "duration_ms": execution.duration_ms
            }

        except Exception as e:
            logger.error(f"Graph workflow execution error: {e}")
            execution.status = WorkflowExecutionStatus.FAILED
            execution.error_message = str(e)
            execution.completed_at = datetime.utcnow()
            execution.duration_ms = (time.time() - start_time) * 1000

            self.db.workflow_executions.insert_one(execution.dict(by_alias=True))

            return {
                "success": False,
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "error": str(e)
            }

    async def _execute_graph_node(
        self,
        node: WorkflowNode,
        context: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """
        Execute a single node in the graph workflow

        Args:
            node: Node to execute
            context: Current execution context
            user_id: User ID

        Returns:
            Node execution result
        """
        start_time = time.time()
        node_start = datetime.utcnow()
        node_data = node.data

        try:
            result = {"success": True, "output": None}

            if node.type == "trigger":
                # Trigger nodes just pass through - they're entry points
                result = {
                    "success": True,
                    "output": {"triggered": True, "trigger_type": node_data.get("triggerType")}
                }

            elif node.type == "condition":
                # Evaluate condition
                condition_type = node_data.get("conditionType", "if")
                config = node_data.get("config", {})

                if condition_type in ["if", "filter", "validation"]:
                    # Evaluate conditions from config
                    conditions = config.get("conditions", [])
                    if conditions:
                        condition_result = ConditionEvaluator.evaluate_conditions_advanced(
                            conditions,
                            context
                        )
                    else:
                        # Check simple field/operator/value
                        field = config.get("field", "")
                        operator = config.get("operator", "equals")
                        value = config.get("value", "")
                        condition_result = self._evaluate_simple_condition(
                            context, field, operator, value
                        )

                    result = {
                        "success": True,
                        "output": {"condition_result": condition_result},
                        "condition_result": condition_result
                    }

                elif condition_type == "switch":
                    # Switch/case evaluation
                    field = config.get("field", "")
                    field_value = self._get_nested_value(context, field)
                    cases = config.get("cases", [])

                    matched_case = None
                    for case in cases:
                        if str(field_value) == str(case.get("value")):
                            matched_case = case.get("value")
                            break

                    result = {
                        "success": True,
                        "output": {"matched_case": matched_case, "field_value": field_value},
                        "matched_case": matched_case
                    }

                elif condition_type == "dedup":
                    # Deduplication check
                    dedup_key = config.get("dedup_key", "")
                    dedup_value = self._get_nested_value(context, dedup_key)

                    # Check if value exists in dedup collection
                    existing = self.db.workflow_dedup.find_one({
                        "user_id": user_id,
                        "key": dedup_key,
                        "value": dedup_value
                    })

                    if existing:
                        result = {
                            "success": True,
                            "output": {"is_duplicate": True, "dedup_key": dedup_key},
                            "condition_result": False  # Don't proceed if duplicate
                        }
                    else:
                        # Store dedup entry
                        self.db.workflow_dedup.insert_one({
                            "user_id": user_id,
                            "key": dedup_key,
                            "value": dedup_value,
                            "created_at": datetime.utcnow()
                        })
                        result = {
                            "success": True,
                            "output": {"is_duplicate": False, "dedup_key": dedup_key},
                            "condition_result": True
                        }

            elif node.type == "code":
                # Execute code node
                code_type = node_data.get("codeType", "custom")
                config = node_data.get("config", {})

                if code_type == "extract_fields":
                    # Extract fields from context
                    fields_to_extract = config.get("fields", [])
                    extracted = {}
                    for field in fields_to_extract:
                        extracted[field] = self._get_nested_value(context, field)
                    context["extracted"] = extracted
                    result = {"success": True, "output": extracted}

                elif code_type == "generate_key":
                    # Generate unique key
                    import uuid
                    key_prefix = config.get("prefix", "key")
                    generated_key = f"{key_prefix}_{uuid.uuid4().hex[:12]}"
                    context["generated_key"] = generated_key
                    result = {"success": True, "output": {"generated_key": generated_key}}

                elif code_type == "increment":
                    # Increment counter
                    counter_name = config.get("counter_name", "counter")
                    increment_by = config.get("increment_by", 1)

                    counter = self.db.workflow_counters.find_one_and_update(
                        {"user_id": user_id, "name": counter_name},
                        {"$inc": {"value": increment_by}},
                        upsert=True,
                        return_document=True
                    )
                    context[counter_name] = counter.get("value", 0)
                    result = {"success": True, "output": {"counter_value": counter.get("value", 0)}}

                elif code_type == "mark_processed":
                    # Mark item as processed
                    process_key = config.get("process_key", "id")
                    process_value = self._get_nested_value(context, process_key)

                    self.db.workflow_processed.insert_one({
                        "user_id": user_id,
                        "key": process_key,
                        "value": process_value,
                        "processed_at": datetime.utcnow()
                    })
                    result = {"success": True, "output": {"marked_processed": True}}

                elif code_type == "custom":
                    # Custom code execution (safely)
                    # For now, just evaluate simple expressions
                    expression = config.get("expression", "")
                    output_variable = config.get("output_variable", "result")

                    # Simple template substitution
                    output = self._render_template(expression, context)
                    context[output_variable] = output
                    result = {"success": True, "output": {output_variable: output}}

            elif node.type == "action":
                # Execute action
                action_type = node_data.get("actionType", "")
                config = node_data.get("config", {})

                # Map visual builder action types to engine action types
                action_type_map = {
                    "send_email": ActionType.SEND_EMAIL,
                    "gmail": ActionType.SEND_EMAIL,
                    "slack_message": ActionType.SEND_SLACK_MESSAGE,
                    "slack": ActionType.SEND_SLACK_MESSAGE,
                    "create_jira": ActionType.CREATE_JIRA_TICKET,
                    "jira_create": ActionType.CREATE_JIRA_TICKET,
                    "jira_update": ActionType.UPDATE_JIRA_TICKET,
                    "update_jira": ActionType.UPDATE_JIRA_TICKET,
                    "hubspot_contact": ActionType.CREATE_HUBSPOT_CONTACT,
                    "hubspot_note": ActionType.CREATE_HUBSPOT_NOTE,
                    "http_request": ActionType.CALL_WEBHOOK,
                    "database": ActionType.UPDATE_DATABASE,
                    "delay": ActionType.DELAY,
                    "respond": None,  # Response nodes end the workflow
                }

                mapped_action_type = action_type_map.get(action_type)

                if action_type == "respond":
                    # Response node - end of workflow path
                    response_type = config.get("responseType", "ok")
                    result = {
                        "success": True,
                        "output": {"response_type": response_type, "end_of_path": True}
                    }

                elif action_type == "delay":
                    # Delay action
                    delay_seconds = config.get("delay_seconds", 60)
                    # In graph mode, we'll handle delays differently
                    result = {
                        "success": True,
                        "output": {"delayed": True, "delay_seconds": delay_seconds}
                    }

                elif action_type == "http_request":
                    # HTTP webhook request
                    import aiohttp
                    url = self._render_template(config.get("url", ""), context)
                    method = config.get("method", "POST")
                    headers = config.get("headers", {})
                    body = config.get("body", {})

                    # Render body templates
                    rendered_body = {}
                    for key, value in body.items():
                        if isinstance(value, str):
                            rendered_body[key] = self._render_template(value, context)
                        else:
                            rendered_body[key] = value

                    async with aiohttp.ClientSession() as session:
                        async with session.request(
                            method=method,
                            url=url,
                            headers=headers,
                            json=rendered_body
                        ) as response:
                            response_data = await response.json() if response.content_type == 'application/json' else await response.text()
                            result = {
                                "success": response.status < 400,
                                "output": {
                                    "status_code": response.status,
                                    "response": response_data
                                }
                            }

                elif action_type == "slack_message":
                    # Send Slack message via webhook
                    import aiohttp
                    webhook_url = config.get("webhook_url", "")
                    message = self._render_template(config.get("message", ""), context)
                    channel = config.get("channel", "")

                    payload = {"text": message}
                    if channel:
                        payload["channel"] = channel

                    async with aiohttp.ClientSession() as session:
                        async with session.post(webhook_url, json=payload) as response:
                            result = {
                                "success": response.status == 200,
                                "output": {"slack_sent": response.status == 200}
                            }

                elif mapped_action_type:
                    # Use existing action executor
                    action_dict = {
                        "type": mapped_action_type,
                        "config": config,
                        "integration_id": config.get("integration_id")
                    }
                    action_result = await self.execute_action(action_dict, context, user_id)
                    result = {
                        "success": action_result.get("success", False),
                        "output": action_result.get("output_data"),
                        "error": action_result.get("error_message")
                    }

                else:
                    result = {
                        "success": False,
                        "error": f"Unknown action type: {action_type}"
                    }

            return {
                "node_id": node.id,
                "node_type": node.type,
                "status": "success" if result.get("success") else "failed",
                "started_at": node_start,
                "completed_at": datetime.utcnow(),
                "duration_ms": (time.time() - start_time) * 1000,
                "output_data": result.get("output"),
                "error_message": result.get("error"),
                "success": result.get("success", False),
                **{k: v for k, v in result.items() if k not in ["success", "output", "error"]}
            }

        except Exception as e:
            logger.error(f"Node execution error ({node.id}): {e}")
            return {
                "node_id": node.id,
                "node_type": node.type,
                "status": "failed",
                "started_at": node_start,
                "completed_at": datetime.utcnow(),
                "duration_ms": (time.time() - start_time) * 1000,
                "error_message": str(e),
                "success": False
            }

    def _get_next_nodes(
        self,
        current_node: WorkflowNode,
        outgoing_edges: List[WorkflowEdge],
        node_result: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[str]:
        """
        Determine which nodes to execute next based on current node result

        Args:
            current_node: Current node that was executed
            outgoing_edges: Edges leaving this node
            node_result: Result of current node execution
            context: Execution context

        Returns:
            List of next node IDs to execute
        """
        if not outgoing_edges:
            return []

        next_nodes = []

        if current_node.type == "condition":
            # For condition nodes, follow the appropriate branch
            condition_result = node_result.get("condition_result", True)
            condition_type = current_node.data.get("conditionType", "if")

            if condition_type == "switch":
                # Switch nodes use matched_case to determine path
                matched_case = node_result.get("matched_case")
                for edge in outgoing_edges:
                    # sourceHandle indicates which case this edge is for
                    if edge.sourceHandle == matched_case or edge.sourceHandle == "default":
                        next_nodes.append(edge.target)
            else:
                # If/filter nodes use true/false branches
                for edge in outgoing_edges:
                    if condition_result and edge.sourceHandle in ["true", None, ""]:
                        next_nodes.append(edge.target)
                    elif not condition_result and edge.sourceHandle == "false":
                        next_nodes.append(edge.target)

        else:
            # For other nodes, follow all outgoing edges
            for edge in outgoing_edges:
                next_nodes.append(edge.target)

        return next_nodes

    def _evaluate_simple_condition(
        self,
        context: Dict[str, Any],
        field: str,
        operator: str,
        value: Any
    ) -> bool:
        """Evaluate a simple condition"""
        field_value = self._get_nested_value(context, field)

        if operator == "equals":
            return str(field_value) == str(value)
        elif operator == "not_equals":
            return str(field_value) != str(value)
        elif operator == "contains":
            return str(value) in str(field_value)
        elif operator == "not_contains":
            return str(value) not in str(field_value)
        elif operator == "greater_than":
            return float(field_value) > float(value)
        elif operator == "less_than":
            return float(field_value) < float(value)
        elif operator == "exists":
            return field_value is not None
        elif operator == "not_exists":
            return field_value is None
        elif operator == "starts_with":
            return str(field_value).startswith(str(value))
        elif operator == "ends_with":
            return str(field_value).endswith(str(value))

        return True

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get a nested value from a dict using dot notation"""
        if not path:
            return None

        keys = path.split(".")
        value = data

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None

        return value

    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        """
        Render a template string with context values

        Supports {{field.name}} syntax
        """
        import re

        def replace_match(match):
            path = match.group(1).strip()
            value = self._get_nested_value(context, path)
            return str(value) if value is not None else ""

        return re.sub(r"\{\{(.+?)\}\}", replace_match, template)

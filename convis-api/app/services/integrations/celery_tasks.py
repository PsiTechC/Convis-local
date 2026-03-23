"""
Celery Tasks for Delayed Workflow Execution
"""
import logging
from datetime import datetime
from typing import Dict, Any
from bson import ObjectId

from app.config.celery_config import celery_app
from app.config.database import Database
from app.models.workflow import Workflow, WorkflowAction

logger = logging.getLogger(__name__)


@celery_app.task(name="execute_delayed_workflow", bind=True, max_retries=3)
def execute_delayed_workflow(self, workflow_id: str, trigger_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a workflow after a delay

    Args:
        workflow_id: ID of the workflow to execute
        trigger_data: Original trigger data

    Returns:
        Execution result
    """
    try:
        from app.services.integrations.workflow_engine import WorkflowEngine
        import asyncio

        logger.info(f"Executing delayed workflow: {workflow_id}")

        db = Database.get_db()
        workflow_doc = db.workflows.find_one({"_id": ObjectId(workflow_id)})

        if not workflow_doc:
            logger.error(f"Workflow {workflow_id} not found")
            return {"success": False, "error": "Workflow not found"}

        workflow = Workflow(**workflow_doc)

        # Execute workflow
        engine = WorkflowEngine()
        result = asyncio.run(engine.execute_workflow(workflow, trigger_data))

        logger.info(f"Delayed workflow executed: {workflow_id}, status: {result.get('status')}")
        return result

    except Exception as e:
        logger.error(f"Error executing delayed workflow {workflow_id}: {e}")
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@celery_app.task(name="execute_delayed_action", bind=True, max_retries=3)
def execute_delayed_action(
    self,
    workflow_id: str,
    action_data: Dict[str, Any],
    context_data: Dict[str, Any],
    user_id: str
) -> Dict[str, Any]:
    """
    Execute a single action after a delay

    Args:
        workflow_id: ID of the workflow this action belongs to
        action_data: Action configuration
        context_data: Context data for template rendering
        user_id: User ID

    Returns:
        Action execution result
    """
    try:
        from app.services.integrations.workflow_engine import WorkflowEngine
        import asyncio

        logger.info(f"Executing delayed action: {action_data.get('type')} for workflow {workflow_id}")

        # Execute action
        engine = WorkflowEngine()
        result = asyncio.run(engine.execute_action(action_data, context_data, user_id))

        logger.info(f"Delayed action executed: {action_data.get('type')}, success: {result.get('success')}")
        return result

    except Exception as e:
        logger.error(f"Error executing delayed action: {e}")
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@celery_app.task(name="continue_workflow_after_delay", bind=True, max_retries=3)
def continue_workflow_after_delay(
    self,
    workflow_id: str,
    remaining_actions: list,
    context_data: Dict[str, Any],
    user_id: str,
    execution_id: str
) -> Dict[str, Any]:
    """
    Continue workflow execution after a delay

    Args:
        workflow_id: ID of the workflow
        remaining_actions: Actions to execute after delay
        context_data: Context data for template rendering
        user_id: User ID
        execution_id: Current execution ID

    Returns:
        Execution result
    """
    try:
        from app.services.integrations.workflow_engine import WorkflowEngine
        import asyncio

        logger.info(f"Continuing workflow {workflow_id} after delay, {len(remaining_actions)} actions remaining")

        db = Database.get_db()

        # Update execution status
        db.workflow_executions.update_one(
            {"_id": execution_id},
            {
                "$set": {
                    "status": "running",
                    "updated_at": datetime.utcnow()
                }
            }
        )

        # Execute remaining actions
        engine = WorkflowEngine()
        action_results = []

        for action_data in remaining_actions:
            try:
                result = asyncio.run(engine.execute_action(action_data, context_data, user_id))
                action_results.append(result)

                # Stop if action failed and error handling is "stop"
                if not result.get("success") and action_data.get("on_error") == "stop":
                    logger.error(f"Action failed, stopping workflow: {result.get('error')}")
                    break

            except Exception as e:
                logger.error(f"Error executing action: {e}")
                action_results.append({
                    "action_type": action_data.get("type"),
                    "success": False,
                    "error": str(e)
                })

                if action_data.get("on_error") == "stop":
                    break

        # Update execution with results
        success_count = sum(1 for r in action_results if r.get("success", False))
        total_count = len(action_results)

        status = "completed" if success_count == total_count else "partial_success" if success_count > 0 else "failed"

        db.workflow_executions.update_one(
            {"_id": execution_id},
            {
                "$set": {
                    "status": status,
                    "completed_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                },
                "$push": {
                    "actions_executed": {"$each": action_results}
                }
            }
        )

        logger.info(f"Workflow continuation completed: {status} ({success_count}/{total_count} actions succeeded)")

        return {
            "success": success_count > 0,
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "status": status,
            "actions_executed": total_count,
            "actions_succeeded": success_count
        }

    except Exception as e:
        logger.error(f"Error continuing workflow after delay: {e}")
        # Update execution status
        db = Database.get_db()
        db.workflow_executions.update_one(
            {"_id": execution_id},
            {
                "$set": {
                    "status": "failed",
                    "error_message": str(e),
                    "completed_at": datetime.utcnow()
                }
            }
        )
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))

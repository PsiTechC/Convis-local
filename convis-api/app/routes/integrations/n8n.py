"""
n8n Integration API Routes

Provides endpoints to:
- Proxy n8n API requests (for frontend)
- Get n8n connection status
- List workflows and executions
- Trigger webhooks manually
- User-specific workflow management
"""

from fastapi import APIRouter, HTTPException, status, Query, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
from bson import ObjectId
from app.services.integrations.n8n_service import n8n_service
from app.utils.auth import get_current_user
from app.config.database import Database
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Request/Response Models ====================

class WebhookTriggerRequest(BaseModel):
    webhook_path: str
    data: Dict[str, Any]
    is_test: bool = False


class WebhookTriggerResponse(BaseModel):
    success: bool
    message: str
    response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class N8NStatusResponse(BaseModel):
    enabled: bool
    healthy: bool
    api_url: str
    webhook_url: str
    error: Optional[str] = None


class WorkflowListResponse(BaseModel):
    success: bool
    data: List[Dict[str, Any]]
    nextCursor: Optional[str] = None
    error: Optional[str] = None


class ExecutionListResponse(BaseModel):
    success: bool
    data: List[Dict[str, Any]]
    nextCursor: Optional[str] = None
    error: Optional[str] = None


# ==================== Endpoints ====================

@router.get("/status", response_model=N8NStatusResponse)
async def get_n8n_status():
    """
    Get n8n integration status and health
    """
    try:
        health = await n8n_service.health_check()

        return N8NStatusResponse(
            enabled=n8n_service.is_enabled(),
            healthy=health.get("healthy", False),
            api_url=n8n_service.api_url,
            webhook_url=n8n_service.webhook_url,
            error=health.get("error")
        )

    except Exception as e:
        logger.error(f"Error checking n8n status: {e}")
        return N8NStatusResponse(
            enabled=n8n_service.is_enabled(),
            healthy=False,
            api_url=n8n_service.api_url,
            webhook_url=n8n_service.webhook_url,
            error=str(e)
        )


@router.get("/workflows", response_model=WorkflowListResponse)
async def list_workflows(
    active_only: bool = Query(False, description="Only return active workflows"),
    limit: int = Query(100, ge=1, le=250, description="Maximum workflows to return")
):
    """
    List all n8n workflows
    """
    try:
        result = await n8n_service.list_workflows(active_only=active_only, limit=limit)

        return WorkflowListResponse(
            success=result.get("success", False),
            data=result.get("data", []),
            nextCursor=result.get("nextCursor"),
            error=result.get("error")
        )

    except Exception as e:
        logger.error(f"Error listing n8n workflows: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list workflows: {str(e)}"
        )


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    """
    Get a specific n8n workflow by ID
    """
    try:
        workflow = await n8n_service.get_workflow(workflow_id)

        if workflow:
            return {"success": True, "data": workflow}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting n8n workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get workflow: {str(e)}"
        )


@router.post("/workflows/{workflow_id}/activate")
async def activate_workflow(workflow_id: str):
    """
    Activate an n8n workflow
    """
    try:
        success = await n8n_service.activate_workflow(workflow_id)

        if success:
            return {"success": True, "message": "Workflow activated"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to activate workflow"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating n8n workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to activate workflow: {str(e)}"
        )


@router.post("/workflows/{workflow_id}/deactivate")
async def deactivate_workflow(workflow_id: str):
    """
    Deactivate an n8n workflow
    """
    try:
        success = await n8n_service.deactivate_workflow(workflow_id)

        if success:
            return {"success": True, "message": "Workflow deactivated"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to deactivate workflow"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating n8n workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deactivate workflow: {str(e)}"
        )


@router.get("/executions", response_model=ExecutionListResponse)
async def list_executions(
    workflow_id: Optional[str] = Query(None, description="Filter by workflow ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (success, error, waiting)"),
    limit: int = Query(50, ge=1, le=250, description="Maximum executions to return")
):
    """
    List n8n workflow executions
    """
    try:
        result = await n8n_service.get_executions(
            workflow_id=workflow_id,
            status=status_filter,
            limit=limit
        )

        return ExecutionListResponse(
            success=result.get("success", False),
            data=result.get("data", []),
            nextCursor=result.get("nextCursor"),
            error=result.get("error")
        )

    except Exception as e:
        logger.error(f"Error listing n8n executions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list executions: {str(e)}"
        )


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: str):
    """
    Get a specific n8n execution by ID
    """
    try:
        execution = await n8n_service.get_execution(execution_id)

        if execution:
            return {"success": True, "data": execution}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Execution not found"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting n8n execution: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get execution: {str(e)}"
        )


@router.post("/webhook/trigger", response_model=WebhookTriggerResponse)
async def trigger_webhook(request: WebhookTriggerRequest):
    """
    Manually trigger an n8n webhook

    Useful for testing webhooks from the frontend
    """
    try:
        result = await n8n_service.trigger_webhook(
            webhook_path=request.webhook_path,
            data=request.data,
            is_test=request.is_test
        )

        return WebhookTriggerResponse(
            success=result.get("success", False),
            message="Webhook triggered" if result.get("success") else "Webhook failed",
            response=result.get("response"),
            error=result.get("error")
        )

    except Exception as e:
        logger.error(f"Error triggering n8n webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger webhook: {str(e)}"
        )


@router.get("/editor-url")
async def get_editor_url():
    """
    Get the n8n editor URL for embedding in iframe

    Returns different URLs for various n8n pages
    """
    try:
        import os
        # Use the n8n editor base URL from environment (GCP Cloud Run URL)
        base_url = os.getenv("N8N_EDITOR_BASE_URL", "https://n8n-custom-1035304851064.europe-west1.run.app")

        return {
            "success": True,
            "urls": {
                "editor": base_url,
                "new_workflow": f"{base_url}/workflow/new",
                "workflows": f"{base_url}/workflows",
                "executions": f"{base_url}/executions",
                "credentials": f"{base_url}/credentials",
                "settings": f"{base_url}/settings"
            },
            "embed_enabled": True,
            "external": True  # Indicates this is an external URL, not proxied
        }

    except Exception as e:
        logger.error(f"Error getting n8n editor URL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get editor URL: {str(e)}"
        )


# ==================== User-Specific Workflow Endpoints ====================

class CreateWorkflowFromTemplateRequest(BaseModel):
    template_id: str
    name: str
    config: Optional[Dict[str, Any]] = None


class UserWorkflowResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    active: bool
    trigger_type: str
    template_id: str
    created_at: str
    updated_at: str
    execution_count: int = 0
    last_execution: Optional[Dict[str, Any]] = None


# Workflow templates configuration
WORKFLOW_TEMPLATES = {
    "send-email-after-call": {
        "name": "Send Email After Call",
        "description": "Automatically send a follow-up email after each completed call",
        "trigger_type": "call_completed",
        "category": "Communication",
        "default_config": {
            "email_template": "follow_up",
            "include_transcript": True,
            "include_summary": True,
        }
    },
    "create-calendar-event": {
        "name": "Create Calendar Event",
        "description": "Book appointments in Google/Outlook calendar when call ends",
        "trigger_type": "call_completed",
        "category": "Scheduling",
        "default_config": {
            "calendar_provider": "google",
            "duration_minutes": 30,
        }
    },
    "slack-notification": {
        "name": "Slack Notification",
        "description": "Send call summaries and alerts to your Slack channel",
        "trigger_type": "call_completed",
        "category": "Notifications",
        "default_config": {
            "channel": "#calls",
            "include_sentiment": True,
        }
    },
    "update-crm": {
        "name": "Update CRM",
        "description": "Sync call data to HubSpot, Salesforce, or other CRMs",
        "trigger_type": "call_completed",
        "category": "CRM",
        "default_config": {
            "crm_provider": "hubspot",
            "create_contact": True,
            "log_activity": True,
        }
    },
    "custom-webhook": {
        "name": "Custom Webhook",
        "description": "Send call data to any external API or service",
        "trigger_type": "call_completed",
        "category": "Integration",
        "default_config": {
            "webhook_url": "",
            "method": "POST",
            "headers": {},
        }
    },
}


@router.get("/user-workflows")
async def get_user_workflows(current_user: dict = Depends(get_current_user)):
    """
    Get all workflows for the current user
    """
    try:
        db = Database.get_db()
        user_workflows_collection = db['user_workflows']

        user_id = str(current_user.get('_id'))

        # Find all workflows for this user
        workflows = list(user_workflows_collection.find(
            {"user_id": user_id}
        ).sort("created_at", -1))

        # Convert ObjectId to string and format response
        formatted_workflows = []
        for wf in workflows:
            formatted_workflows.append({
                "id": str(wf['_id']),
                "name": wf.get('name', ''),
                "description": wf.get('description', ''),
                "active": wf.get('active', False),
                "trigger_type": wf.get('trigger_type', 'call_completed'),
                "template_id": wf.get('template_id', ''),
                "config": wf.get('config', {}),
                "created_at": wf.get('created_at', datetime.utcnow()).isoformat(),
                "updated_at": wf.get('updated_at', datetime.utcnow()).isoformat(),
                "execution_count": wf.get('execution_count', 0),
                "last_execution": wf.get('last_execution'),
            })

        return {"workflows": formatted_workflows}

    except Exception as e:
        logger.error(f"Error fetching user workflows: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch workflows: {str(e)}"
        )


@router.post("/user-workflows/create-from-template")
async def create_workflow_from_template(
    request: CreateWorkflowFromTemplateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new workflow from a template for the current user
    """
    try:
        # Validate template exists
        template = WORKFLOW_TEMPLATES.get(request.template_id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid template ID: {request.template_id}"
            )

        db = Database.get_db()
        user_workflows_collection = db['user_workflows']

        user_id = str(current_user.get('_id'))

        # Create workflow document
        workflow_doc = {
            "user_id": user_id,
            "name": request.name or template['name'],
            "description": template['description'],
            "template_id": request.template_id,
            "trigger_type": template['trigger_type'],
            "category": template['category'],
            "active": True,
            "config": {**template['default_config'], **(request.config or {})},
            "execution_count": 0,
            "last_execution": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        # Insert into database
        result = user_workflows_collection.insert_one(workflow_doc)

        # Return created workflow
        workflow_doc['_id'] = result.inserted_id
        return {
            "success": True,
            "workflow": {
                "id": str(result.inserted_id),
                "name": workflow_doc['name'],
                "description": workflow_doc['description'],
                "active": workflow_doc['active'],
                "trigger_type": workflow_doc['trigger_type'],
                "template_id": workflow_doc['template_id'],
                "config": workflow_doc['config'],
                "created_at": workflow_doc['created_at'].isoformat(),
                "updated_at": workflow_doc['updated_at'].isoformat(),
                "execution_count": 0,
                "last_execution": None,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating workflow from template: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create workflow: {str(e)}"
        )


@router.post("/user-workflows/{workflow_id}/activate")
async def activate_user_workflow(
    workflow_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Activate a user's workflow
    """
    try:
        db = Database.get_db()
        user_workflows_collection = db['user_workflows']

        user_id = str(current_user.get('_id'))

        # Update workflow
        result = user_workflows_collection.update_one(
            {"_id": ObjectId(workflow_id), "user_id": user_id},
            {"$set": {"active": True, "updated_at": datetime.utcnow()}}
        )

        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found"
            )

        return {"success": True, "message": "Workflow activated"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating user workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to activate workflow: {str(e)}"
        )


@router.post("/user-workflows/{workflow_id}/deactivate")
async def deactivate_user_workflow(
    workflow_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Deactivate a user's workflow
    """
    try:
        db = Database.get_db()
        user_workflows_collection = db['user_workflows']

        user_id = str(current_user.get('_id'))

        # Update workflow
        result = user_workflows_collection.update_one(
            {"_id": ObjectId(workflow_id), "user_id": user_id},
            {"$set": {"active": False, "updated_at": datetime.utcnow()}}
        )

        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found"
            )

        return {"success": True, "message": "Workflow deactivated"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating user workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deactivate workflow: {str(e)}"
        )


@router.delete("/user-workflows/{workflow_id}")
async def delete_user_workflow(
    workflow_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a user's workflow
    """
    try:
        db = Database.get_db()
        user_workflows_collection = db['user_workflows']

        user_id = str(current_user.get('_id'))

        # Delete workflow
        result = user_workflows_collection.delete_one(
            {"_id": ObjectId(workflow_id), "user_id": user_id}
        )

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found"
            )

        return {"success": True, "message": "Workflow deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete workflow: {str(e)}"
        )


class UpdateWorkflowRequest(BaseModel):
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


@router.put("/user-workflows/{workflow_id}")
async def update_user_workflow(
    workflow_id: str,
    request: UpdateWorkflowRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Update a user's workflow configuration
    """
    try:
        db = Database.get_db()
        user_workflows_collection = db['user_workflows']

        user_id = str(current_user.get('_id'))

        # Build update document
        update_fields = {"updated_at": datetime.utcnow()}
        if request.name:
            update_fields["name"] = request.name
        if request.config:
            update_fields["config"] = request.config

        # Update workflow
        result = user_workflows_collection.update_one(
            {"_id": ObjectId(workflow_id), "user_id": user_id},
            {"$set": update_fields}
        )

        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found"
            )

        return {"success": True, "message": "Workflow updated"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update workflow: {str(e)}"
        )


@router.get("/user-workflows/{workflow_id}")
async def get_user_workflow(
    workflow_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get a specific workflow for the current user
    """
    try:
        db = Database.get_db()
        user_workflows_collection = db['user_workflows']

        user_id = str(current_user.get('_id'))

        # Find workflow
        workflow = user_workflows_collection.find_one(
            {"_id": ObjectId(workflow_id), "user_id": user_id}
        )

        if not workflow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found"
            )

        return {
            "workflow": {
                "id": str(workflow['_id']),
                "name": workflow.get('name', ''),
                "description": workflow.get('description', ''),
                "active": workflow.get('active', False),
                "trigger_type": workflow.get('trigger_type', 'call_completed'),
                "template_id": workflow.get('template_id', ''),
                "config": workflow.get('config', {}),
                "created_at": workflow.get('created_at', datetime.utcnow()).isoformat(),
                "updated_at": workflow.get('updated_at', datetime.utcnow()).isoformat(),
                "execution_count": workflow.get('execution_count', 0),
                "last_execution": workflow.get('last_execution'),
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch workflow: {str(e)}"
        )

"""
Workflow Management API Routes
Handles CRUD operations for workflows and workflow executions
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
import logging

from app.config.database import Database
from app.models.workflow import (
    Workflow, WorkflowExecution, TriggerEvent, WorkflowCondition, WorkflowAction, GraphData
)
from app.middleware.auth import get_current_user
from app.services.integrations.workflow_engine import WorkflowEngine
from app.services.integrations.n8n_importer import N8nImporter
from typing import Dict, Any
from fastapi import UploadFile, File

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_workflow(
    workflow_data: dict,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Create a new workflow"""
    try:
        db = Database.get_db()

        # Validate trigger event
        trigger_event = workflow_data.get("trigger_event")
        if not trigger_event or trigger_event not in [t.value for t in TriggerEvent]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid trigger event"
            )

        # Check if this is a graph-based workflow (visual builder)
        graph_data = workflow_data.get("graph_data")
        actions = workflow_data.get("actions", [])

        # For graph-based workflows, actions can be empty (derived from graph)
        # For legacy workflows, require at least one action
        if not graph_data and not actions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one action or graph_data is required"
            )

        # Create workflow
        workflow = Workflow(
            user_id=str(current_user["_id"]),
            name=workflow_data.get("name"),
            description=workflow_data.get("description"),
            trigger_event=trigger_event,
            trigger_config=workflow_data.get("trigger_config"),
            conditions=workflow_data.get("conditions", []),
            actions=actions,
            graph_data=graph_data,
            # Webhook/n8n integration fields
            webhook_url=workflow_data.get("webhook_url"),
            n8n_workflow_id=workflow_data.get("n8n_workflow_id"),
            n8n_base_url=workflow_data.get("n8n_base_url"),
            is_active=workflow_data.get("is_active", True),
            priority=workflow_data.get("priority", 0),
            metadata=workflow_data.get("metadata", {})
        )

        # Insert into database
        result = db.workflows.insert_one(workflow.dict(by_alias=True, exclude={"id"}))
        workflow_id = str(result.inserted_id)

        logger.info(f"Created workflow {workflow_id} for user {current_user['_id']}")

        return {
            "success": True,
            "workflow_id": workflow_id,
            "message": "Workflow created successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/")
async def get_workflows(
    trigger_event: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get all workflows for current user"""
    try:
        db = Database.get_db()

        query = {"user_id": str(current_user["_id"])}
        if trigger_event:
            query["trigger_event"] = trigger_event
        if is_active is not None:
            query["is_active"] = is_active

        workflows = list(db.workflows.find(query).sort("created_at", -1))

        for workflow in workflows:
            workflow["_id"] = str(workflow["_id"])

        return {
            "success": True,
            "workflows": workflows,
            "count": len(workflows)
        }

    except Exception as e:
        logger.error(f"Error fetching workflows: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/workflow-stats")
async def get_workflow_statistics(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get workflow statistics for current user"""
    try:
        db = Database.get_db()

        # Get total workflows
        total_workflows = db.workflows.count_documents({
            "user_id": str(current_user["_id"])
        })

        active_workflows = db.workflows.count_documents({
            "user_id": str(current_user["_id"]),
            "is_active": True
        })

        # Get execution stats
        total_executions = db.workflow_executions.count_documents({
            "user_id": str(current_user["_id"])
        })

        successful_executions = db.workflow_executions.count_documents({
            "user_id": str(current_user["_id"]),
            "status": "completed"
        })

        failed_executions = db.workflow_executions.count_documents({
            "user_id": str(current_user["_id"]),
            "status": "failed"
        })

        # Get recent executions
        recent_executions = list(
            db.workflow_executions.find({
                "user_id": str(current_user["_id"])
            })
            .sort("started_at", -1)
            .limit(10)
        )

        for execution in recent_executions:
            execution["_id"] = str(execution["_id"])

        return {
            "success": True,
            "statistics": {
                "total_workflows": total_workflows,
                "active_workflows": active_workflows,
                "total_executions": total_executions,
                "successful_executions": successful_executions,
                "failed_executions": failed_executions,
                "success_rate": (successful_executions / total_executions * 100) if total_executions > 0 else 0
            },
            "recent_executions": recent_executions
        }

    except Exception as e:
        logger.error(f"Error fetching statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/executions")
async def get_all_executions(
    limit: int = 100,
    trigger_event: Optional[str] = None,
    status: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get all workflow executions for current user"""
    try:
        db = Database.get_db()

        query = {"user_id": str(current_user["_id"])}
        if trigger_event:
            query["trigger_event"] = trigger_event
        if status:
            query["status"] = status

        executions = list(
            db.workflow_executions.find(query)
            .sort("started_at", -1)
            .limit(limit)
        )

        for execution in executions:
            execution["_id"] = str(execution["_id"])

        return {
            "success": True,
            "executions": executions,
            "count": len(executions)
        }

    except Exception as e:
        logger.error(f"Error fetching executions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get a specific workflow"""
    try:
        db = Database.get_db()

        workflow = db.workflows.find_one({
            "_id": ObjectId(workflow_id),
            "user_id": str(current_user["_id"])
        })

        if not workflow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found"
            )

        workflow["_id"] = str(workflow["_id"])

        return {
            "success": True,
            "workflow": workflow
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put("/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    update_data: dict,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Update a workflow"""
    try:
        db = Database.get_db()

        # Check ownership
        existing = db.workflows.find_one({
            "_id": ObjectId(workflow_id),
            "user_id": str(current_user["_id"])
        })

        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found"
            )

        # Prepare update
        update_fields = {}
        allowed_fields = [
            "name", "description", "trigger_config", "conditions",
            "actions", "is_active", "priority", "metadata", "graph_data",
            "webhook_url", "n8n_workflow_id", "n8n_base_url"  # Webhook/n8n integration fields
        ]

        for field in allowed_fields:
            if field in update_data:
                update_fields[field] = update_data[field]

        update_fields["updated_at"] = datetime.utcnow()

        # Update
        db.workflows.update_one(
            {"_id": ObjectId(workflow_id)},
            {"$set": update_fields}
        )

        logger.info(f"Updated workflow {workflow_id}")

        return {
            "success": True,
            "message": "Workflow updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Delete a workflow"""
    try:
        db = Database.get_db()

        result = db.workflows.delete_one({
            "_id": ObjectId(workflow_id),
            "user_id": str(current_user["_id"])
        })

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found"
            )

        logger.info(f"Deleted workflow {workflow_id}")

        return {
            "success": True,
            "message": "Workflow deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{workflow_id}/toggle")
async def toggle_workflow(
    workflow_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Toggle workflow active status"""
    try:
        db = Database.get_db()

        workflow = db.workflows.find_one({
            "_id": ObjectId(workflow_id),
            "user_id": str(current_user["_id"])
        })

        if not workflow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found"
            )

        new_status = not workflow.get("is_active", True)

        db.workflows.update_one(
            {"_id": ObjectId(workflow_id)},
            {
                "$set": {
                    "is_active": new_status,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        return {
            "success": True,
            "is_active": new_status,
            "message": f"Workflow {'activated' if new_status else 'deactivated'}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{workflow_id}/execute")
async def manual_execute_workflow(
    workflow_id: str,
    trigger_data: dict,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Manually execute a workflow"""
    try:
        db = Database.get_db()

        workflow_doc = db.workflows.find_one({
            "_id": ObjectId(workflow_id),
            "user_id": str(current_user["_id"])
        })

        if not workflow_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found"
            )

        workflow = Workflow(**workflow_doc)

        # Execute workflow
        engine = WorkflowEngine()
        result = await engine.execute_workflow(workflow, trigger_data)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{workflow_id}/executions")
async def get_workflow_executions(
    workflow_id: str,
    limit: int = 50,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get execution history for a workflow"""
    try:
        db = Database.get_db()

        # Verify ownership
        workflow = db.workflows.find_one({
            "_id": ObjectId(workflow_id),
            "user_id": str(current_user["_id"])
        })

        if not workflow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found"
            )

        # Get executions
        executions = list(
            db.workflow_executions.find({
                "workflow_id": workflow_id
            })
            .sort("started_at", -1)
            .limit(limit)
        )

        for execution in executions:
            execution["_id"] = str(execution["_id"])

        return {
            "success": True,
            "executions": executions,
            "count": len(executions)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching executions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/executions/{execution_id}")
async def get_execution_details(
    execution_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get details of a specific workflow execution"""
    try:
        db = Database.get_db()

        execution = db.workflow_executions.find_one({
            "_id": execution_id,
            "user_id": str(current_user["_id"])
        })

        if not execution:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Execution not found"
            )

        execution["_id"] = str(execution["_id"])

        return {
            "success": True,
            "execution": execution
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching execution: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/webhook/{workflow_id}/trigger")
async def trigger_workflow_via_webhook(
    workflow_id: str,
    trigger_data: dict,
    webhook_token: Optional[str] = None
):
    """
    Generic webhook endpoint to trigger workflows from external systems

    This endpoint allows external systems (Zapier, Make.com, custom apps) to trigger Convis workflows.

    Security: Requires workflow_id and optional webhook_token for authentication

    Example:
        POST /api/workflows/webhook/{workflow_id}/trigger
        Authorization: Bearer {webhook_token}

        {
            "customer_email": "john@example.com",
            "customer_name": "John Doe",
            "custom_data": {...}
        }
    """
    try:
        db = Database.get_db()

        # Get workflow
        workflow_doc = db.workflows.find_one({
            "_id": ObjectId(workflow_id)
        })

        if not workflow_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found"
            )

        # Verify workflow is active
        if not workflow_doc.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Workflow is not active"
            )

        # Optional: Verify webhook token (if configured in workflow metadata)
        configured_token = workflow_doc.get("metadata", {}).get("webhook_token")
        if configured_token and webhook_token != configured_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook token"
            )

        workflow = Workflow(**workflow_doc)

        # Add timestamp and webhook metadata
        enriched_trigger_data = {
            **trigger_data.get("trigger_data", trigger_data),
            "webhook_triggered": True,
            "trigger_source": "external_webhook",
            "timestamp": datetime.utcnow().isoformat()
        }

        # Execute workflow
        engine = WorkflowEngine()
        result = await engine.execute_workflow(workflow, enriched_trigger_data)

        logger.info(f"Workflow {workflow_id} triggered via webhook")

        return {
            "success": True,
            "execution_id": result.get("execution_id"),
            "status": result.get("status"),
            "message": "Workflow triggered successfully via webhook"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering workflow via webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ==================== N8N IMPORT ENDPOINTS ====================

@router.post("/import/n8n/validate")
async def validate_n8n_workflow(
    workflow_json: dict,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Validate an n8n workflow JSON before importing

    Returns validation status and workflow preview
    """
    try:
        is_valid, message, parsed_data = N8nImporter.validate_n8n_json(workflow_json)

        if not is_valid:
            return {
                "success": False,
                "valid": False,
                "message": message
            }

        # Get preview information
        nodes = parsed_data.get("nodes", [])
        connections = parsed_data.get("connections", {})

        # Extract credentials needed
        credentials_info = N8nImporter.extract_credentials_info(parsed_data)

        # Get node type summary
        node_types = {}
        for node in nodes:
            n8n_type = node.get("type", "unknown")
            mapping = N8nImporter.get_node_mapping(n8n_type)
            category = mapping.get("category", "Other")

            if category not in node_types:
                node_types[category] = []
            node_types[category].append({
                "name": node.get("name"),
                "type": n8n_type,
                "mapped_to": mapping.get("label", "Custom Node")
            })

        return {
            "success": True,
            "valid": True,
            "message": message,
            "preview": {
                "name": parsed_data.get("name", "Unnamed Workflow"),
                "node_count": len(nodes),
                "connection_count": sum(
                    len(conns)
                    for outputs in connections.values()
                    for output_list in outputs.values()
                    for conns in output_list
                ),
                "nodes_by_category": node_types,
                "credentials_required": credentials_info
            }
        }

    except Exception as e:
        logger.error(f"Error validating n8n workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/import/n8n", status_code=status.HTTP_201_CREATED)
async def import_n8n_workflow(
    workflow_json: dict,
    workflow_name: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Import an n8n workflow JSON and convert to Convis format

    The workflow will be created in disabled state until credentials are configured.
    """
    try:
        db = Database.get_db()
        user_id = str(current_user["_id"])

        # Validate first
        is_valid, message, _ = N8nImporter.validate_n8n_json(workflow_json)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message
            )

        # Import and convert
        convis_workflow = N8nImporter.import_workflow(
            workflow_json,
            user_id,
            workflow_name
        )

        # Insert into database
        result = db.workflows.insert_one(convis_workflow)
        workflow_id = str(result.inserted_id)

        # Get credentials requirements
        credentials_required = convis_workflow.get("metadata", {}).get("credentials_required", [])

        logger.info(f"Imported n8n workflow as {workflow_id} for user {user_id}")

        return {
            "success": True,
            "workflow_id": workflow_id,
            "message": "n8n workflow imported successfully",
            "workflow_name": convis_workflow["name"],
            "node_count": convis_workflow["metadata"]["node_count"],
            "edge_count": convis_workflow["metadata"]["edge_count"],
            "credentials_required": credentials_required,
            "is_active": False,
            "next_steps": [
                "Configure required integrations in Settings > Integrations" if credentials_required else None,
                "Review and customize the imported workflow in Visual Builder",
                "Enable the workflow once configured"
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing n8n workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/import/n8n/file", status_code=status.HTTP_201_CREATED)
async def import_n8n_workflow_file(
    file: UploadFile = File(...),
    workflow_name: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Import an n8n workflow from uploaded JSON file

    Accepts .json files exported from n8n
    """
    try:
        # Validate file type
        if not file.filename.endswith('.json'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be a JSON file (.json)"
            )

        # Read file content
        content = await file.read()
        try:
            import json
            workflow_json = json.loads(content.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON file: {e}"
            )

        db = Database.get_db()
        user_id = str(current_user["_id"])

        # Validate
        is_valid, message, _ = N8nImporter.validate_n8n_json(workflow_json)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message
            )

        # Import and convert
        convis_workflow = N8nImporter.import_workflow(
            workflow_json,
            user_id,
            workflow_name
        )

        # Insert into database
        result = db.workflows.insert_one(convis_workflow)
        workflow_id = str(result.inserted_id)

        credentials_required = convis_workflow.get("metadata", {}).get("credentials_required", [])

        logger.info(f"Imported n8n workflow file '{file.filename}' as {workflow_id}")

        return {
            "success": True,
            "workflow_id": workflow_id,
            "message": f"n8n workflow '{file.filename}' imported successfully",
            "workflow_name": convis_workflow["name"],
            "node_count": convis_workflow["metadata"]["node_count"],
            "edge_count": convis_workflow["metadata"]["edge_count"],
            "credentials_required": credentials_required,
            "is_active": False
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing n8n workflow file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/import/n8n/supported-nodes")
async def get_supported_n8n_nodes():
    """
    Get list of supported n8n node types and their Convis mappings

    Useful for showing users what n8n nodes are supported
    """
    try:
        # Group by category
        categories = {}

        for n8n_type, mapping in N8nImporter.NODE_TYPE_MAP.items():
            category = mapping.get("category", "Other")
            if category not in categories:
                categories[category] = []

            categories[category].append({
                "n8n_type": n8n_type,
                "convis_type": mapping.get("type"),
                "label": mapping.get("label"),
                "icon": mapping.get("icon")
            })

        return {
            "success": True,
            "total_supported": len(N8nImporter.NODE_TYPE_MAP),
            "categories": categories
        }

    except Exception as e:
        logger.error(f"Error getting supported nodes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

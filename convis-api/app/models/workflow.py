"""
Workflow Model
Stores workflow definitions and execution history
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum


class TriggerEvent(str, Enum):
    """Available workflow trigger events"""
    CALL_COMPLETED = "call_completed"
    CALL_FAILED = "call_failed"
    CALL_NO_ANSWER = "call_no_answer"
    CALL_BUSY = "call_busy"
    CALL_VOICEMAIL = "call_voicemail"
    CAMPAIGN_COMPLETED = "campaign_completed"
    WEBHOOK = "webhook"
    MANUAL = "manual"


# ==================== Graph-Based Workflow Models ====================

class WorkflowNode(BaseModel):
    """Node in a visual workflow graph"""
    id: str = Field(..., description="Unique node ID")
    type: str = Field(..., description="Node type: trigger, condition, action, code")
    position: Dict[str, float] = Field(..., description="Node position {x, y}")
    data: Dict[str, Any] = Field(..., description="Node-specific data and config")


class WorkflowEdge(BaseModel):
    """Edge connecting nodes in a workflow graph"""
    id: str = Field(..., description="Unique edge ID")
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    sourceHandle: Optional[str] = Field(None, description="Source handle ID (for branches)")
    targetHandle: Optional[str] = Field(None, description="Target handle ID")


class ConditionOperator(str, Enum):
    """Condition comparison operators"""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    MATCHES_REGEX = "matches_regex"


class ActionType(str, Enum):
    """Available workflow actions"""
    CREATE_JIRA_TICKET = "create_jira_ticket"
    UPDATE_JIRA_TICKET = "update_jira_ticket"
    CREATE_HUBSPOT_CONTACT = "create_hubspot_contact"
    UPDATE_HUBSPOT_CONTACT = "update_hubspot_contact"
    CREATE_HUBSPOT_NOTE = "create_hubspot_note"
    SEND_EMAIL = "send_email"
    SEND_SLACK_MESSAGE = "send_slack_message"
    CALL_WEBHOOK = "call_webhook"
    UPDATE_DATABASE = "update_database"
    RUN_SCRIPT = "run_script"
    DELAY = "delay"  # Delay action
    BRANCH = "branch"  # Conditional branching (if-else)
    LOOP = "loop"  # Loop/for-each iteration


class WorkflowCondition(BaseModel):
    """Single condition in a workflow filter"""
    field: str = Field(..., description="Field to check (supports dot notation)")
    operator: ConditionOperator = Field(..., description="Comparison operator")
    value: Any = Field(..., description="Value to compare against")
    logic: Optional[str] = Field("AND", description="Logic operator (AND/OR) for next condition")


class WorkflowAction(BaseModel):
    """Single action in a workflow"""
    id: Optional[str] = Field(None, description="Unique action ID")
    type: ActionType = Field(..., description="Action type")
    integration_id: Optional[str] = Field(None, description="Integration to use (if applicable)")
    config: Dict[str, Any] = Field(..., description="Action-specific configuration")
    condition: Optional[List[WorkflowCondition]] = Field(None, description="Optional action-level conditions")
    on_error: Optional[str] = Field("continue", description="Error handling: continue, stop, retry")
    retry_count: Optional[int] = Field(0, description="Number of retries on failure")
    timeout_seconds: Optional[int] = Field(30, description="Action timeout in seconds")

    # Delay-specific fields
    delay_seconds: Optional[int] = Field(None, description="Delay duration in seconds (for DELAY action)")
    delay_until: Optional[datetime] = Field(None, description="Execute at specific time (for DELAY action)")

    # Branch-specific fields (for conditional branching)
    branch_conditions: Optional[List[WorkflowCondition]] = Field(None, description="Conditions for 'if' branch")
    if_actions: Optional[List['WorkflowAction']] = Field(None, description="Actions to run if conditions are true")
    else_actions: Optional[List['WorkflowAction']] = Field(None, description="Actions to run if conditions are false")

    # Loop-specific fields (for iteration)
    loop_array_field: Optional[str] = Field(None, description="Field name containing array to loop over")
    loop_item_variable: Optional[str] = Field("item", description="Variable name for current item in loop")
    loop_index_variable: Optional[str] = Field("index", description="Variable name for current index in loop")
    loop_actions: Optional[List['WorkflowAction']] = Field(None, description="Actions to run for each item")
    loop_max_iterations: Optional[int] = Field(100, description="Maximum iterations to prevent infinite loops")


class GraphData(BaseModel):
    """Visual workflow graph data for the builder UI"""
    nodes: List[WorkflowNode] = Field([], description="List of workflow nodes")
    edges: List[WorkflowEdge] = Field([], description="List of edges connecting nodes")


class Workflow(BaseModel):
    """Workflow definition"""
    id: Optional[str] = Field(None, alias="_id")
    user_id: str = Field(..., description="User ID who owns this workflow")
    name: str = Field(..., description="Workflow name")
    description: Optional[str] = Field(None, description="Workflow description")
    trigger_event: TriggerEvent = Field(..., description="Event that triggers this workflow")
    trigger_config: Optional[Dict[str, Any]] = Field(None, description="Trigger-specific configuration")
    conditions: Optional[List[WorkflowCondition]] = Field([], description="Filter conditions")
    actions: Optional[List[WorkflowAction]] = Field([], description="Actions to execute (legacy format)")

    # Graph-based workflow data (visual builder)
    graph_data: Optional[GraphData] = Field(None, description="Visual workflow graph for drag-drop builder")

    # Webhook/n8n integration fields
    webhook_url: Optional[str] = Field(None, description="Webhook URL for external workflow systems like n8n")
    n8n_workflow_id: Optional[str] = Field(None, description="n8n workflow ID for direct n8n integration")
    n8n_base_url: Optional[str] = Field(None, description="n8n base URL if different from default")

    is_active: bool = Field(True, description="Whether this workflow is active")
    priority: int = Field(0, description="Execution priority (higher runs first)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_executed_at: Optional[datetime] = Field(None, description="Last execution timestamp")
    last_execution_status: Optional[str] = Field(None, description="Status of last execution")
    last_execution_error: Optional[str] = Field(None, description="Error from last execution if failed")
    execution_count: int = Field(0, description="Total executions")
    success_count: int = Field(0, description="Successful executions")
    failure_count: int = Field(0, description="Failed executions")

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class WorkflowExecutionStatus(str, Enum):
    """Workflow execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL_SUCCESS = "partial_success"


class ActionExecution(BaseModel):
    """Individual action execution result"""
    action_id: str
    action_type: ActionType
    status: str = Field(..., description="success, failed, skipped")
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int = Field(0, description="Number of retries attempted")


class WorkflowExecution(BaseModel):
    """Workflow execution record"""
    id: Optional[str] = Field(None, alias="_id")
    workflow_id: str = Field(..., description="Workflow that was executed")
    user_id: str = Field(..., description="User who owns the workflow")
    trigger_event: TriggerEvent = Field(..., description="Event that triggered execution")
    trigger_data: Dict[str, Any] = Field(..., description="Event data that triggered workflow")
    status: WorkflowExecutionStatus = Field(WorkflowExecutionStatus.PENDING)
    conditions_met: bool = Field(True, description="Whether filter conditions passed")
    actions_executed: List[ActionExecution] = Field([], description="Action execution results")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(None)
    duration_ms: Optional[float] = None
    error_message: Optional[str] = Field(None, description="Overall error message")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

    # Related entities
    call_id: Optional[str] = Field(None, description="Related call ID")
    campaign_id: Optional[str] = Field(None, description="Related campaign ID")

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class WorkflowTemplate(BaseModel):
    """Pre-built workflow template"""
    id: Optional[str] = Field(None, alias="_id")
    name: str = Field(..., description="Template name")
    description: str = Field(..., description="Template description")
    category: str = Field(..., description="Template category (e.g., 'customer_support', 'sales')")
    icon: Optional[str] = Field(None, description="Icon identifier")
    trigger_event: TriggerEvent
    conditions: List[WorkflowCondition] = Field([])
    actions: List[WorkflowAction] = Field([])
    required_integrations: List[str] = Field([], description="Required integration types")
    is_public: bool = Field(True, description="Whether template is publicly available")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    usage_count: int = Field(0, description="Number of times this template was used")

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

from pydantic import BaseModel
from typing import Optional

class InboundCallConfig(BaseModel):
    """Configuration for inbound call handling"""
    assistant_id: str
    system_message: str
    voice: str
    temperature: float

class InboundCallResponse(BaseModel):
    """Response for inbound call endpoint"""
    message: str
    config: Optional[InboundCallConfig] = None

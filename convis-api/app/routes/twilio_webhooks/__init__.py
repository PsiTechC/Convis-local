from fastapi import APIRouter
from app.routes.twilio_webhooks import webhooks

router = APIRouter()
router.include_router(webhooks.router)

__all__ = ['router']

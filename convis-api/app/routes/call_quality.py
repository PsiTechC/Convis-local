"""
Call Quality API Routes

Provides endpoints for:
1. Getting call quality metrics for a specific call
2. Getting aggregate quality metrics for an assistant
3. Getting quality alerts history
4. Getting quality thresholds configuration
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.config.database import Database
from app.utils.auth import get_current_user

import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Response Models ---

class NetworkMetricsResponse(BaseModel):
    """Network quality metrics"""
    packet_loss_percent: float = Field(description="Percentage of lost packets")
    jitter_ms: float = Field(description="Average jitter in milliseconds")
    jitter_max_ms: float = Field(description="Maximum jitter observed")
    rtt_ms: float = Field(description="Average round-trip time in milliseconds")
    packets_sent: int = Field(description="Total packets sent")
    packets_received: int = Field(description="Total packets received")
    packets_lost: int = Field(description="Total packets lost")


class AudioMetricsResponse(BaseModel):
    """Audio quality metrics"""
    snr_db: float = Field(description="Signal-to-noise ratio in dB")
    rms_db: float = Field(description="Average RMS level in dB")
    peak_db: float = Field(description="Peak audio level in dB")
    silence_percent: float = Field(description="Percentage of call that was silence")
    voice_activity_percent: float = Field(description="Percentage of call with voice activity")
    total_chunks: int = Field(description="Total audio chunks processed")


class QualityScoreResponse(BaseModel):
    """Quality score metrics"""
    mos: float = Field(description="Mean Opinion Score (1-5)")
    overall_quality: str = Field(description="Quality rating: excellent/good/fair/poor")
    alert_count: int = Field(description="Number of quality alerts during call")


class CallQualityResponse(BaseModel):
    """Complete call quality report"""
    call_id: str
    network: NetworkMetricsResponse
    audio: AudioMetricsResponse
    quality: QualityScoreResponse
    duration_seconds: float
    recorded_at: Optional[datetime] = None


class QualityAlertResponse(BaseModel):
    """Quality alert record"""
    timestamp: datetime
    severity: str = Field(description="Alert severity: warning/critical")
    metric: str = Field(description="Metric that triggered the alert")
    value: float = Field(description="Value that triggered the alert")
    threshold: float = Field(description="Threshold that was exceeded")
    message: str = Field(description="Human-readable alert message")


class AggregateQualityResponse(BaseModel):
    """Aggregate quality metrics for an assistant or time period"""
    total_calls: int
    avg_mos: float
    avg_packet_loss_percent: float
    avg_jitter_ms: float
    avg_snr_db: float
    quality_distribution: Dict[str, int] = Field(description="Count by quality rating")
    alert_count: int
    time_period: str


class QualityThresholdsResponse(BaseModel):
    """Quality threshold configuration"""
    max_packet_loss_percent: float
    max_jitter_ms: float
    max_rtt_ms: float
    min_snr_db: float
    min_mos: float


# --- API Endpoints ---

@router.get("/calls/{call_id}/quality", response_model=CallQualityResponse)
async def get_call_quality(
    call_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get quality metrics for a specific call.

    Returns network quality (packet loss, jitter, RTT), audio quality (SNR, RMS),
    and overall quality score (MOS).
    """
    db = Database.get_db()
    call_logs = db['call_logs']

    # Find the call log
    call_log = call_logs.find_one({
        "call_id": call_id,
        "user_id": str(current_user["_id"])
    })

    if not call_log:
        # Try to find by _id if call_id doesn't match
        if ObjectId.is_valid(call_id):
            call_log = call_logs.find_one({
                "_id": ObjectId(call_id),
                "user_id": str(current_user["_id"])
            })

    if not call_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call not found or you don't have access to it"
        )

    # Get quality report from call log
    quality_report = call_log.get("quality_report", {})

    if not quality_report:
        # Return default values if no quality data available
        quality_report = {
            "network": {
                "packet_loss_percent": 0.0,
                "jitter_ms": 0.0,
                "jitter_max_ms": 0.0,
                "rtt_ms": 0.0,
                "packets_sent": 0,
                "packets_received": 0,
                "packets_lost": 0
            },
            "audio": {
                "snr_db": 0.0,
                "rms_db": -60.0,
                "peak_db": -60.0,
                "silence_percent": 0.0,
                "voice_activity_percent": 0.0,
                "total_chunks": 0
            },
            "quality": {
                "mos": 0.0,
                "overall_quality": "unknown",
                "alert_count": 0
            }
        }

    return CallQualityResponse(
        call_id=call_id,
        network=NetworkMetricsResponse(**quality_report.get("network", {})),
        audio=AudioMetricsResponse(**quality_report.get("audio", {})),
        quality=QualityScoreResponse(**quality_report.get("quality", {})),
        duration_seconds=call_log.get("duration_seconds", 0),
        recorded_at=call_log.get("created_at")
    )


@router.get("/assistants/{assistant_id}/quality", response_model=AggregateQualityResponse)
async def get_assistant_quality(
    assistant_id: str,
    timeframe: str = Query("last_7d", pattern="^(last_7d|last_30d|last_90d|total)$"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get aggregate quality metrics for an assistant.

    Returns average MOS, packet loss, jitter, and quality distribution
    over the specified time period.
    """
    db = Database.get_db()
    call_logs = db['call_logs']

    # Build date filter
    date_filter = {}
    now = datetime.utcnow()

    if timeframe == "last_7d":
        date_filter["created_at"] = {"$gte": now - timedelta(days=7)}
    elif timeframe == "last_30d":
        date_filter["created_at"] = {"$gte": now - timedelta(days=30)}
    elif timeframe == "last_90d":
        date_filter["created_at"] = {"$gte": now - timedelta(days=90)}
    # "total" means no date filter

    # Find all calls for this assistant
    query = {
        "assistant_id": assistant_id,
        "user_id": str(current_user["_id"]),
        **date_filter
    }

    calls = list(call_logs.find(query))

    if not calls:
        return AggregateQualityResponse(
            total_calls=0,
            avg_mos=0.0,
            avg_packet_loss_percent=0.0,
            avg_jitter_ms=0.0,
            avg_snr_db=0.0,
            quality_distribution={"excellent": 0, "good": 0, "fair": 0, "poor": 0},
            alert_count=0,
            time_period=timeframe
        )

    # Calculate aggregate metrics
    mos_values = []
    packet_loss_values = []
    jitter_values = []
    snr_values = []
    quality_distribution = {"excellent": 0, "good": 0, "fair": 0, "poor": 0, "unknown": 0}
    total_alerts = 0

    for call in calls:
        quality_report = call.get("quality_report", {})
        if quality_report:
            quality = quality_report.get("quality", {})
            network = quality_report.get("network", {})
            audio = quality_report.get("audio", {})

            if quality.get("mos"):
                mos_values.append(quality["mos"])
            if network.get("packet_loss_percent") is not None:
                packet_loss_values.append(network["packet_loss_percent"])
            if network.get("jitter_ms") is not None:
                jitter_values.append(network["jitter_ms"])
            if audio.get("snr_db"):
                snr_values.append(audio["snr_db"])

            overall = quality.get("overall_quality", "unknown")
            if overall in quality_distribution:
                quality_distribution[overall] += 1

            total_alerts += quality.get("alert_count", 0)

    # Remove unknown if zero
    if quality_distribution["unknown"] == 0:
        del quality_distribution["unknown"]

    return AggregateQualityResponse(
        total_calls=len(calls),
        avg_mos=sum(mos_values) / len(mos_values) if mos_values else 0.0,
        avg_packet_loss_percent=sum(packet_loss_values) / len(packet_loss_values) if packet_loss_values else 0.0,
        avg_jitter_ms=sum(jitter_values) / len(jitter_values) if jitter_values else 0.0,
        avg_snr_db=sum(snr_values) / len(snr_values) if snr_values else 0.0,
        quality_distribution=quality_distribution,
        alert_count=total_alerts,
        time_period=timeframe
    )


@router.get("/calls/{call_id}/quality/alerts", response_model=List[QualityAlertResponse])
async def get_call_quality_alerts(
    call_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get quality alerts that occurred during a specific call.

    Returns a list of all quality alerts including packet loss spikes,
    high jitter, low SNR, and other quality degradation events.
    """
    db = Database.get_db()
    call_logs = db['call_logs']

    # Find the call log
    call_log = call_logs.find_one({
        "call_id": call_id,
        "user_id": str(current_user["_id"])
    })

    if not call_log:
        if ObjectId.is_valid(call_id):
            call_log = call_logs.find_one({
                "_id": ObjectId(call_id),
                "user_id": str(current_user["_id"])
            })

    if not call_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call not found or you don't have access to it"
        )

    # Get alerts from quality report
    quality_report = call_log.get("quality_report", {})
    alerts_data = quality_report.get("alerts", [])

    alerts = []
    for alert in alerts_data:
        alerts.append(QualityAlertResponse(
            timestamp=alert.get("timestamp", datetime.utcnow()),
            severity=alert.get("severity", "warning"),
            metric=alert.get("metric", "unknown"),
            value=alert.get("value", 0.0),
            threshold=alert.get("threshold", 0.0),
            message=alert.get("message", "")
        ))

    return alerts


@router.get("/quality/thresholds", response_model=QualityThresholdsResponse)
async def get_quality_thresholds(
    current_user: dict = Depends(get_current_user)
):
    """
    Get the current QoS thresholds configuration.

    These thresholds determine when quality alerts are triggered.
    """
    db = Database.get_db()
    users = db['users']

    user = users.find_one({"_id": current_user["_id"]})

    # Get user's custom thresholds or use defaults
    settings = user.get("quality_settings", {}) if user else {}

    return QualityThresholdsResponse(
        max_packet_loss_percent=settings.get("max_packet_loss_percent", 3.0),
        max_jitter_ms=settings.get("max_jitter_ms", 30.0),
        max_rtt_ms=settings.get("max_rtt_ms", 300.0),
        min_snr_db=settings.get("min_snr_db", 10.0),
        min_mos=settings.get("min_mos", 3.0)
    )


@router.put("/quality/thresholds", response_model=QualityThresholdsResponse)
async def update_quality_thresholds(
    thresholds: QualityThresholdsResponse,
    current_user: dict = Depends(get_current_user)
):
    """
    Update the QoS thresholds configuration.

    Customize when quality alerts are triggered based on your requirements.
    """
    db = Database.get_db()
    users = db['users']

    # Update user's quality settings
    users.update_one(
        {"_id": current_user["_id"]},
        {
            "$set": {
                "quality_settings": {
                    "max_packet_loss_percent": thresholds.max_packet_loss_percent,
                    "max_jitter_ms": thresholds.max_jitter_ms,
                    "max_rtt_ms": thresholds.max_rtt_ms,
                    "min_snr_db": thresholds.min_snr_db,
                    "min_mos": thresholds.min_mos,
                    "updated_at": datetime.utcnow()
                }
            }
        }
    )

    logger.info(f"Updated quality thresholds for user {current_user['_id']}")

    return thresholds


@router.get("/quality/summary", response_model=Dict)
async def get_quality_summary(
    timeframe: str = Query("last_7d", pattern="^(last_7d|last_30d|last_90d|total)$"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a summary of call quality across all assistants.

    Returns overall quality statistics and trends.
    """
    db = Database.get_db()
    call_logs = db['call_logs']

    # Build date filter
    date_filter = {}
    now = datetime.utcnow()

    if timeframe == "last_7d":
        date_filter["created_at"] = {"$gte": now - timedelta(days=7)}
    elif timeframe == "last_30d":
        date_filter["created_at"] = {"$gte": now - timedelta(days=30)}
    elif timeframe == "last_90d":
        date_filter["created_at"] = {"$gte": now - timedelta(days=90)}

    # Find all calls for this user
    query = {
        "user_id": str(current_user["_id"]),
        **date_filter
    }

    calls = list(call_logs.find(query))

    # Calculate summary statistics
    total_calls = len(calls)
    calls_with_quality = 0
    total_mos = 0.0
    quality_breakdown = {"excellent": 0, "good": 0, "fair": 0, "poor": 0}
    total_alerts = 0

    for call in calls:
        quality_report = call.get("quality_report", {})
        if quality_report:
            calls_with_quality += 1
            quality = quality_report.get("quality", {})

            mos = quality.get("mos", 0)
            if mos > 0:
                total_mos += mos

            overall = quality.get("overall_quality", "unknown")
            if overall in quality_breakdown:
                quality_breakdown[overall] += 1

            total_alerts += quality.get("alert_count", 0)

    avg_mos = total_mos / calls_with_quality if calls_with_quality > 0 else 0.0

    # Determine overall health
    if avg_mos >= 4.0:
        overall_health = "excellent"
    elif avg_mos >= 3.5:
        overall_health = "good"
    elif avg_mos >= 3.0:
        overall_health = "fair"
    else:
        overall_health = "poor" if calls_with_quality > 0 else "no_data"

    return {
        "time_period": timeframe,
        "total_calls": total_calls,
        "calls_with_quality_data": calls_with_quality,
        "average_mos": round(avg_mos, 2),
        "overall_health": overall_health,
        "quality_breakdown": quality_breakdown,
        "total_alerts": total_alerts,
        "alerts_per_call": round(total_alerts / calls_with_quality, 2) if calls_with_quality > 0 else 0
    }

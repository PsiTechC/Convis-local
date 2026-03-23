"""
Latency monitoring for voice pipeline (Bolna-inspired)
Tracks ASR → LLM → TTS latency and logs bottlenecks
"""
import time
import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class LatencyMonitor:
    """Monitor and log latency for each stage of the voice pipeline"""

    def __init__(self, call_sid: str):
        self.call_sid = call_sid
        self.stages: Dict[str, Dict] = {}
        self.call_start = time.time()

    def start_stage(self, stage_name: str) -> None:
        """Mark the start of a pipeline stage"""
        self.stages[stage_name] = {
            'start': time.time(),
            'end': None,
            'duration_ms': None
        }

    def end_stage(self, stage_name: str) -> float:
        """Mark the end of a pipeline stage and return duration"""
        if stage_name not in self.stages:
            logger.warning(f"Stage {stage_name} not found in latency monitor")
            return 0

        stage = self.stages[stage_name]
        stage['end'] = time.time()
        stage['duration_ms'] = (stage['end'] - stage['start']) * 1000

        # Log if latency is high
        if stage['duration_ms'] > 1000:  # > 1 second
            logger.warning(
                f"⚠️  High latency in {stage_name}: {stage['duration_ms']:.0f}ms "
                f"(call: {self.call_sid})"
            )

        return stage['duration_ms']

    def get_total_latency(self) -> float:
        """Get total latency from call start to now"""
        return (time.time() - self.call_start) * 1000

    def log_summary(self) -> None:
        """Log a summary of all stage latencies"""
        total_call_duration = self.get_total_latency()

        logger.info(f"📊 Latency Summary for call {self.call_sid}:")
        logger.info(f"   Total call duration: {total_call_duration:.0f}ms")

        for stage_name, stage_data in self.stages.items():
            if stage_data['duration_ms'] is not None:
                logger.info(
                    f"   {stage_name}: {stage_data['duration_ms']:.0f}ms"
                )

    def get_metrics(self) -> Dict:
        """Get all metrics as a dictionary for database storage"""
        return {
            'call_sid': self.call_sid,
            'total_duration_ms': self.get_total_latency(),
            'stages': {
                name: data['duration_ms']
                for name, data in self.stages.items()
                if data['duration_ms'] is not None
            },
            'timestamp': datetime.utcnow()
        }


class PipelineStageTimer:
    """Context manager for timing pipeline stages"""

    def __init__(self, monitor: LatencyMonitor, stage_name: str):
        self.monitor = monitor
        self.stage_name = stage_name

    def __enter__(self):
        self.monitor.start_stage(self.stage_name)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = self.monitor.end_stage(self.stage_name)
        if duration > 500:  # > 500ms
            logger.info(f"⏱️  {self.stage_name}: {duration:.0f}ms")
        return False

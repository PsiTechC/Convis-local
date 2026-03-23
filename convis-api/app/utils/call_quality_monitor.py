"""
Call Quality Monitor - Comprehensive call quality tracking and alerting

Features:
1. Network Quality Metrics: Packet loss, jitter, RTT tracking
2. Audio Quality Assessment: SNR, RMS levels, silence detection, MOS estimation
3. QoS Thresholds & Alerts: Configurable thresholds with callback alerts
4. Composite Quality Score: Overall call quality rating (1-5 MOS scale)

Usage:
    monitor = CallQualityMonitor(call_id="call_123")
    monitor.set_alert_callback(my_alert_handler)

    # During call - track audio chunks
    monitor.track_audio_chunk(audio_data, timestamp)

    # Track network events
    monitor.track_packet_sent(seq_num, timestamp)
    monitor.track_packet_received(seq_num, timestamp)

    # Get quality report
    report = monitor.get_quality_report()
"""

import logging
import math
import struct
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class QualityLevel(Enum):
    """Quality level classification"""
    EXCELLENT = "excellent"  # MOS >= 4.0
    GOOD = "good"            # MOS >= 3.5
    FAIR = "fair"            # MOS >= 3.0
    POOR = "poor"            # MOS >= 2.5
    BAD = "bad"              # MOS < 2.5


class AlertType(Enum):
    """Types of quality alerts"""
    HIGH_PACKET_LOSS = "high_packet_loss"
    HIGH_JITTER = "high_jitter"
    HIGH_LATENCY = "high_latency"
    LOW_AUDIO_LEVEL = "low_audio_level"
    HIGH_NOISE = "high_noise"
    EXCESSIVE_SILENCE = "excessive_silence"
    QUALITY_DEGRADATION = "quality_degradation"
    NETWORK_UNSTABLE = "network_unstable"


@dataclass
class QoSThresholds:
    """Configurable QoS thresholds"""
    # Network thresholds
    max_packet_loss_percent: float = 3.0      # Alert if packet loss > 3%
    max_jitter_ms: float = 30.0               # Alert if jitter > 30ms
    max_rtt_ms: float = 300.0                 # Alert if RTT > 300ms

    # Audio thresholds
    min_audio_level_db: float = -50.0         # Alert if audio too quiet
    max_noise_level_db: float = -20.0         # Alert if too much noise
    max_silence_percent: float = 70.0         # Alert if too much silence
    min_snr_db: float = 10.0                  # Alert if SNR too low

    # Quality thresholds
    min_mos_score: float = 3.0                # Alert if MOS drops below 3.0

    # Timing
    alert_cooldown_seconds: float = 10.0      # Min time between same alert type


@dataclass
class NetworkMetrics:
    """Network quality metrics"""
    packets_sent: int = 0
    packets_received: int = 0
    packets_lost: int = 0
    packet_loss_percent: float = 0.0

    # Jitter (inter-packet delay variation)
    jitter_ms: float = 0.0
    jitter_samples: List[float] = field(default_factory=list)

    # Round-trip time
    rtt_ms: float = 0.0
    rtt_samples: List[float] = field(default_factory=list)

    # Timestamps for tracking
    last_packet_time: Optional[float] = None
    packet_intervals: List[float] = field(default_factory=list)


@dataclass
class AudioMetrics:
    """Audio quality metrics"""
    # Levels
    rms_level_db: float = -60.0           # Root Mean Square level
    peak_level_db: float = -60.0          # Peak audio level

    # Signal-to-Noise Ratio
    snr_db: float = 0.0                   # Estimated SNR
    noise_floor_db: float = -60.0         # Background noise level

    # Silence detection
    silence_percent: float = 0.0          # % of audio that's silence
    silence_duration_ms: float = 0.0      # Current silence duration
    total_silence_ms: float = 0.0         # Total silence in call
    total_audio_ms: float = 0.0           # Total audio duration

    # Audio characteristics
    clipping_events: int = 0              # Number of clipping events
    sample_rate: int = 8000               # Audio sample rate

    # Quality indicators
    audio_present: bool = False           # Is audio being received
    voice_detected: bool = False          # Is voice activity detected


@dataclass
class QualityScore:
    """Composite quality score"""
    mos_score: float = 4.0                # Mean Opinion Score (1-5)
    quality_level: QualityLevel = QualityLevel.GOOD
    network_score: float = 100.0          # Network quality (0-100)
    audio_score: float = 100.0            # Audio quality (0-100)
    overall_score: float = 100.0          # Combined score (0-100)


@dataclass
class QualityAlert:
    """Quality alert event"""
    alert_type: AlertType
    severity: str                         # "warning" or "critical"
    message: str
    value: float                          # The metric value that triggered alert
    threshold: float                      # The threshold that was exceeded
    timestamp: datetime = field(default_factory=datetime.now)


class CallQualityMonitor:
    """
    Comprehensive call quality monitoring system.

    Tracks network quality, audio quality, and provides real-time
    quality scores with configurable alerting.
    """

    def __init__(
        self,
        call_id: str,
        thresholds: Optional[QoSThresholds] = None,
        sample_rate: int = 8000,
        alert_callback: Optional[Callable[[QualityAlert], None]] = None
    ):
        self.call_id = call_id
        self.thresholds = thresholds or QoSThresholds()
        self.sample_rate = sample_rate
        self.alert_callback = alert_callback

        # Metrics
        self.network = NetworkMetrics()
        self.audio = AudioMetrics(sample_rate=sample_rate)
        self.quality = QualityScore()

        # Alert tracking
        self.alerts: List[QualityAlert] = []
        self.last_alert_times: Dict[AlertType, float] = {}

        # Packet tracking for loss/jitter calculation
        self.packet_sequence: Dict[int, float] = {}  # seq_num -> send_time
        self.received_packets: set = set()
        self.expected_sequence: int = 0

        # Audio analysis buffers
        self.audio_buffer: Deque[bytes] = deque(maxlen=100)  # Last 100 chunks
        self.noise_samples: Deque[float] = deque(maxlen=50)  # For noise floor estimation
        self.rms_history: Deque[float] = deque(maxlen=100)   # RMS history

        # Timing
        self.start_time = time.time()
        self.last_audio_time: Optional[float] = None
        self.silence_start: Optional[float] = None

        # Quality history for trend analysis
        self.mos_history: Deque[float] = deque(maxlen=60)  # Last 60 samples

        logger.info(f"[QUALITY] CallQualityMonitor initialized for call {call_id}")

    def set_alert_callback(self, callback: Callable[[QualityAlert], None]):
        """Set callback function for quality alerts"""
        self.alert_callback = callback

    # ==================== Network Quality Tracking ====================

    def track_packet_sent(self, sequence_num: int, timestamp: Optional[float] = None):
        """Track an outgoing packet"""
        ts = timestamp or time.time()
        self.packet_sequence[sequence_num] = ts
        self.network.packets_sent += 1

        # Calculate inter-packet interval for jitter
        if self.network.last_packet_time:
            interval = (ts - self.network.last_packet_time) * 1000  # Convert to ms
            self.network.packet_intervals.append(interval)

            # Keep only last 100 intervals
            if len(self.network.packet_intervals) > 100:
                self.network.packet_intervals = self.network.packet_intervals[-100:]

        self.network.last_packet_time = ts

    def track_packet_received(self, sequence_num: int, timestamp: Optional[float] = None):
        """Track a received packet and calculate metrics"""
        ts = timestamp or time.time()

        self.network.packets_received += 1
        self.received_packets.add(sequence_num)

        # Calculate RTT if we have send time
        if sequence_num in self.packet_sequence:
            rtt = (ts - self.packet_sequence[sequence_num]) * 1000  # ms
            self.network.rtt_samples.append(rtt)

            # Keep only last 50 RTT samples
            if len(self.network.rtt_samples) > 50:
                self.network.rtt_samples = self.network.rtt_samples[-50:]

            # Update average RTT
            self.network.rtt_ms = sum(self.network.rtt_samples) / len(self.network.rtt_samples)

        # Calculate packet loss
        self._calculate_packet_loss()

        # Calculate jitter
        self._calculate_jitter()

        # Check for alerts
        self._check_network_alerts()

    def track_packet_loss(self, lost_count: int = 1):
        """Directly track packet loss (for systems that report it)"""
        self.network.packets_lost += lost_count
        self._calculate_packet_loss()
        self._check_network_alerts()

    def _calculate_packet_loss(self):
        """Calculate packet loss percentage"""
        if self.network.packets_sent > 0:
            expected = self.network.packets_sent
            received = self.network.packets_received
            lost = max(0, expected - received)
            self.network.packets_lost = lost
            self.network.packet_loss_percent = (lost / expected) * 100

    def _calculate_jitter(self):
        """Calculate jitter using RFC 3550 algorithm"""
        if len(self.network.packet_intervals) < 2:
            return

        intervals = self.network.packet_intervals

        # Calculate jitter as average absolute deviation from mean interval
        mean_interval = sum(intervals) / len(intervals)
        deviations = [abs(i - mean_interval) for i in intervals]

        if deviations:
            self.network.jitter_ms = sum(deviations) / len(deviations)
            self.network.jitter_samples.append(self.network.jitter_ms)

            # Keep only last 50 jitter samples
            if len(self.network.jitter_samples) > 50:
                self.network.jitter_samples = self.network.jitter_samples[-50:]

    # ==================== Audio Quality Tracking ====================

    def track_audio_chunk(
        self,
        audio_data: bytes,
        timestamp: Optional[float] = None,
        is_voice: bool = False
    ):
        """
        Analyze an audio chunk for quality metrics.

        Args:
            audio_data: Raw PCM audio bytes (16-bit signed)
            timestamp: Optional timestamp
            is_voice: Whether VAD detected voice in this chunk
        """
        ts = timestamp or time.time()

        if not audio_data or len(audio_data) < 2:
            return

        self.audio_buffer.append(audio_data)
        self.audio.audio_present = True
        self.audio.voice_detected = is_voice

        # Convert bytes to numpy array for analysis
        try:
            samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)

            if len(samples) == 0:
                return

            # Calculate RMS level
            rms = self._calculate_rms(samples)
            rms_db = self._to_db(rms)
            self.audio.rms_level_db = rms_db
            self.rms_history.append(rms_db)

            # Calculate peak level
            peak = np.max(np.abs(samples))
            self.audio.peak_level_db = self._to_db(peak)

            # Detect clipping
            if peak >= 32000:  # Near max for 16-bit
                self.audio.clipping_events += 1

            # Update silence tracking
            chunk_duration_ms = (len(samples) / self.sample_rate) * 1000
            self.audio.total_audio_ms += chunk_duration_ms

            silence_threshold_db = -45.0  # Consider below -45dB as silence
            is_silence = rms_db < silence_threshold_db

            if is_silence:
                if self.silence_start is None:
                    self.silence_start = ts
                self.audio.silence_duration_ms = (ts - self.silence_start) * 1000
                self.audio.total_silence_ms += chunk_duration_ms
            else:
                self.silence_start = None
                self.audio.silence_duration_ms = 0

                # Update noise floor estimate (from quiet non-silence sections)
                if rms_db < -30:  # Quiet but not silent
                    self.noise_samples.append(rms_db)

            # Calculate silence percentage
            if self.audio.total_audio_ms > 0:
                self.audio.silence_percent = (
                    self.audio.total_silence_ms / self.audio.total_audio_ms
                ) * 100

            # Estimate noise floor and SNR
            self._update_noise_estimation()

            self.last_audio_time = ts

            # Update quality scores
            self._update_quality_scores()

            # Check for alerts
            self._check_audio_alerts()

        except Exception as e:
            logger.warning(f"[QUALITY] Error analyzing audio: {e}")

    def _calculate_rms(self, samples: np.ndarray) -> float:
        """Calculate Root Mean Square of audio samples"""
        if len(samples) == 0:
            return 0.0
        return np.sqrt(np.mean(samples ** 2))

    def _to_db(self, value: float) -> float:
        """Convert linear value to decibels"""
        if value <= 0:
            return -100.0
        # Reference: max 16-bit value (32767)
        return 20 * math.log10(value / 32767.0)

    def _update_noise_estimation(self):
        """Estimate noise floor and calculate SNR"""
        if len(self.noise_samples) < 5:
            return

        # Noise floor is the lower percentile of quiet samples
        sorted_samples = sorted(self.noise_samples)
        noise_floor_idx = len(sorted_samples) // 4  # 25th percentile
        self.audio.noise_floor_db = sorted_samples[noise_floor_idx]

        # SNR = signal level - noise floor
        if len(self.rms_history) > 0:
            # Use recent RMS average as signal level
            recent_rms = list(self.rms_history)[-10:]
            signal_level = sum(recent_rms) / len(recent_rms)
            self.audio.snr_db = signal_level - self.audio.noise_floor_db

    # ==================== Quality Scoring ====================

    def _update_quality_scores(self):
        """Calculate composite quality scores"""
        # Network score (0-100)
        network_score = 100.0

        # Packet loss impact (each 1% reduces score by 20)
        network_score -= min(self.network.packet_loss_percent * 20, 50)

        # Jitter impact (each 10ms above 20ms reduces score by 10)
        jitter_penalty = max(0, (self.network.jitter_ms - 20) / 10) * 10
        network_score -= min(jitter_penalty, 30)

        # RTT impact (each 50ms above 100ms reduces score by 5)
        rtt_penalty = max(0, (self.network.rtt_ms - 100) / 50) * 5
        network_score -= min(rtt_penalty, 20)

        self.quality.network_score = max(0, network_score)

        # Audio score (0-100)
        audio_score = 100.0

        # SNR impact (below 20dB starts reducing score)
        if self.audio.snr_db < 20:
            snr_penalty = (20 - self.audio.snr_db) * 3
            audio_score -= min(snr_penalty, 40)

        # Silence impact (above 50% starts reducing score)
        if self.audio.silence_percent > 50:
            silence_penalty = (self.audio.silence_percent - 50) * 1
            audio_score -= min(silence_penalty, 30)

        # Low audio level impact
        if self.audio.rms_level_db < -45:
            level_penalty = (-45 - self.audio.rms_level_db) * 2
            audio_score -= min(level_penalty, 20)

        # Clipping penalty
        if self.audio.clipping_events > 0:
            audio_score -= min(self.audio.clipping_events * 2, 10)

        self.quality.audio_score = max(0, audio_score)

        # Overall score (weighted average)
        self.quality.overall_score = (
            self.quality.network_score * 0.4 +
            self.quality.audio_score * 0.6
        )

        # Calculate MOS score (1-5 scale)
        # Based on E-model simplified
        self.quality.mos_score = self._calculate_mos()
        self.mos_history.append(self.quality.mos_score)

        # Determine quality level
        mos = self.quality.mos_score
        if mos >= 4.0:
            self.quality.quality_level = QualityLevel.EXCELLENT
        elif mos >= 3.5:
            self.quality.quality_level = QualityLevel.GOOD
        elif mos >= 3.0:
            self.quality.quality_level = QualityLevel.FAIR
        elif mos >= 2.5:
            self.quality.quality_level = QualityLevel.POOR
        else:
            self.quality.quality_level = QualityLevel.BAD

    def _calculate_mos(self) -> float:
        """
        Calculate Mean Opinion Score (1-5) using simplified E-model.

        This is an estimation based on network and audio metrics.
        """
        # Start with perfect score
        r_factor = 93.2  # R-factor for VoIP

        # Delay impairment (Id)
        delay = self.network.rtt_ms / 2  # One-way delay estimate
        if delay > 177.3:
            id_factor = 0.024 * delay + 0.11 * (delay - 177.3)
        else:
            id_factor = 0.024 * delay
        r_factor -= id_factor

        # Equipment impairment (Ie) - based on codec and packet loss
        # Simplified: assume G.711 codec
        ie_base = 0  # G.711 has no codec impairment

        # Packet loss impairment
        ppl = self.network.packet_loss_percent
        if ppl > 0:
            # Bpl coefficient for random packet loss
            bpl = 25.0  # Typical value for G.711
            ie_eff = ie_base + (95 - ie_base) * ppl / (ppl + bpl)
            r_factor -= ie_eff

        # Jitter impairment (simplified)
        if self.network.jitter_ms > 20:
            jitter_impairment = (self.network.jitter_ms - 20) * 0.5
            r_factor -= min(jitter_impairment, 15)

        # Audio quality adjustment
        if self.audio.snr_db < 15:
            snr_impairment = (15 - self.audio.snr_db) * 1.5
            r_factor -= min(snr_impairment, 20)

        # Convert R-factor to MOS
        if r_factor < 0:
            mos = 1.0
        elif r_factor > 100:
            mos = 4.5
        else:
            mos = 1 + 0.035 * r_factor + r_factor * (r_factor - 60) * (100 - r_factor) * 7e-6

        # Clamp to valid range
        return max(1.0, min(5.0, mos))

    # ==================== Alerting ====================

    def _check_network_alerts(self):
        """Check network metrics against thresholds"""
        now = time.time()

        # High packet loss
        if self.network.packet_loss_percent > self.thresholds.max_packet_loss_percent:
            self._raise_alert(
                AlertType.HIGH_PACKET_LOSS,
                "critical" if self.network.packet_loss_percent > 5 else "warning",
                f"Packet loss at {self.network.packet_loss_percent:.1f}%",
                self.network.packet_loss_percent,
                self.thresholds.max_packet_loss_percent
            )

        # High jitter
        if self.network.jitter_ms > self.thresholds.max_jitter_ms:
            self._raise_alert(
                AlertType.HIGH_JITTER,
                "critical" if self.network.jitter_ms > 50 else "warning",
                f"Jitter at {self.network.jitter_ms:.1f}ms",
                self.network.jitter_ms,
                self.thresholds.max_jitter_ms
            )

        # High latency
        if self.network.rtt_ms > self.thresholds.max_rtt_ms:
            self._raise_alert(
                AlertType.HIGH_LATENCY,
                "critical" if self.network.rtt_ms > 500 else "warning",
                f"RTT at {self.network.rtt_ms:.1f}ms",
                self.network.rtt_ms,
                self.thresholds.max_rtt_ms
            )

    def _check_audio_alerts(self):
        """Check audio metrics against thresholds"""
        # Low audio level
        if self.audio.rms_level_db < self.thresholds.min_audio_level_db:
            self._raise_alert(
                AlertType.LOW_AUDIO_LEVEL,
                "warning",
                f"Audio level very low at {self.audio.rms_level_db:.1f}dB",
                self.audio.rms_level_db,
                self.thresholds.min_audio_level_db
            )

        # Low SNR (high noise)
        if self.audio.snr_db < self.thresholds.min_snr_db:
            self._raise_alert(
                AlertType.HIGH_NOISE,
                "warning",
                f"SNR too low at {self.audio.snr_db:.1f}dB",
                self.audio.snr_db,
                self.thresholds.min_snr_db
            )

        # Excessive silence
        if self.audio.silence_percent > self.thresholds.max_silence_percent:
            self._raise_alert(
                AlertType.EXCESSIVE_SILENCE,
                "warning",
                f"Excessive silence: {self.audio.silence_percent:.1f}%",
                self.audio.silence_percent,
                self.thresholds.max_silence_percent
            )

        # Quality degradation
        if self.quality.mos_score < self.thresholds.min_mos_score:
            self._raise_alert(
                AlertType.QUALITY_DEGRADATION,
                "critical" if self.quality.mos_score < 2.5 else "warning",
                f"Call quality degraded: MOS {self.quality.mos_score:.2f}",
                self.quality.mos_score,
                self.thresholds.min_mos_score
            )

    def _raise_alert(
        self,
        alert_type: AlertType,
        severity: str,
        message: str,
        value: float,
        threshold: float
    ):
        """Raise a quality alert if cooldown has passed"""
        now = time.time()

        # Check cooldown
        last_alert = self.last_alert_times.get(alert_type, 0)
        if now - last_alert < self.thresholds.alert_cooldown_seconds:
            return

        alert = QualityAlert(
            alert_type=alert_type,
            severity=severity,
            message=message,
            value=value,
            threshold=threshold
        )

        self.alerts.append(alert)
        self.last_alert_times[alert_type] = now

        logger.warning(f"[QUALITY] Alert: {severity.upper()} - {message}")

        # Call callback if set
        if self.alert_callback:
            try:
                self.alert_callback(alert)
            except Exception as e:
                logger.error(f"[QUALITY] Alert callback error: {e}")

    # ==================== Reporting ====================

    def get_quality_report(self) -> Dict[str, Any]:
        """Get comprehensive quality report"""
        duration = time.time() - self.start_time

        return {
            "call_id": self.call_id,
            "duration_seconds": duration,
            "timestamp": datetime.now().isoformat(),

            "quality_score": {
                "mos": round(self.quality.mos_score, 2),
                "level": self.quality.quality_level.value,
                "network_score": round(self.quality.network_score, 1),
                "audio_score": round(self.quality.audio_score, 1),
                "overall_score": round(self.quality.overall_score, 1)
            },

            "network_metrics": {
                "packets_sent": self.network.packets_sent,
                "packets_received": self.network.packets_received,
                "packets_lost": self.network.packets_lost,
                "packet_loss_percent": round(self.network.packet_loss_percent, 2),
                "jitter_ms": round(self.network.jitter_ms, 2),
                "rtt_ms": round(self.network.rtt_ms, 2),
                "avg_jitter_ms": round(
                    sum(self.network.jitter_samples) / len(self.network.jitter_samples), 2
                ) if self.network.jitter_samples else 0,
                "avg_rtt_ms": round(
                    sum(self.network.rtt_samples) / len(self.network.rtt_samples), 2
                ) if self.network.rtt_samples else 0
            },

            "audio_metrics": {
                "rms_level_db": round(self.audio.rms_level_db, 1),
                "peak_level_db": round(self.audio.peak_level_db, 1),
                "snr_db": round(self.audio.snr_db, 1),
                "noise_floor_db": round(self.audio.noise_floor_db, 1),
                "silence_percent": round(self.audio.silence_percent, 1),
                "total_silence_ms": round(self.audio.total_silence_ms, 0),
                "total_audio_ms": round(self.audio.total_audio_ms, 0),
                "clipping_events": self.audio.clipping_events,
                "audio_present": self.audio.audio_present
            },

            "alerts": [
                {
                    "type": a.alert_type.value,
                    "severity": a.severity,
                    "message": a.message,
                    "value": a.value,
                    "threshold": a.threshold,
                    "timestamp": a.timestamp.isoformat()
                }
                for a in self.alerts
            ],

            "alert_summary": {
                "total_alerts": len(self.alerts),
                "critical_alerts": sum(1 for a in self.alerts if a.severity == "critical"),
                "warning_alerts": sum(1 for a in self.alerts if a.severity == "warning")
            },

            "quality_trend": {
                "mos_samples": list(self.mos_history),
                "trend": self._calculate_trend()
            }
        }

    def _calculate_trend(self) -> str:
        """Calculate quality trend (improving, stable, degrading)"""
        if len(self.mos_history) < 10:
            return "stable"

        recent = list(self.mos_history)[-10:]
        earlier = list(self.mos_history)[-20:-10] if len(self.mos_history) >= 20 else recent

        recent_avg = sum(recent) / len(recent)
        earlier_avg = sum(earlier) / len(earlier)

        diff = recent_avg - earlier_avg

        if diff > 0.2:
            return "improving"
        elif diff < -0.2:
            return "degrading"
        else:
            return "stable"

    def get_summary(self) -> str:
        """Get a brief text summary of call quality"""
        return (
            f"Call Quality: {self.quality.quality_level.value.upper()} "
            f"(MOS: {self.quality.mos_score:.1f}) | "
            f"Network: {self.quality.network_score:.0f}% | "
            f"Audio: {self.quality.audio_score:.0f}% | "
            f"Packet Loss: {self.network.packet_loss_percent:.1f}% | "
            f"Jitter: {self.network.jitter_ms:.0f}ms | "
            f"SNR: {self.audio.snr_db:.0f}dB"
        )


# Convenience function for quick quality check
def assess_call_quality(
    packet_loss_percent: float = 0,
    jitter_ms: float = 0,
    rtt_ms: float = 0,
    snr_db: float = 30
) -> Tuple[float, QualityLevel]:
    """
    Quick assessment of call quality without full monitoring.

    Returns: (MOS score, Quality Level)
    """
    monitor = CallQualityMonitor(call_id="assessment")

    # Set network metrics directly
    monitor.network.packet_loss_percent = packet_loss_percent
    monitor.network.jitter_ms = jitter_ms
    monitor.network.rtt_ms = rtt_ms
    monitor.audio.snr_db = snr_db

    # Calculate scores
    monitor._update_quality_scores()

    return monitor.quality.mos_score, monitor.quality.quality_level

"""
WebRTC Module for Convis Voice AI

This module provides WebRTC-based voice calling capabilities for:
- Web browser calls (lowest latency)
- Mobile app calls
- Direct peer-to-peer audio streaming

Key advantages over WebSocket:
- 20-50ms latency vs 100-300ms with WebSocket
- Built-in echo cancellation
- Adaptive bitrate
- UDP-based (no TCP head-of-line blocking)

Note: Phone calls (PSTN) still use WebSocket via Twilio/FreJun
"""

from .webrtc_handler import WebRTCVoiceHandler, handle_webrtc_call
from .signaling_server import WebRTCSignalingServer, WebRTCSession, signaling_server
from .ice_config import get_ice_servers, get_rtc_configuration

__all__ = [
    'WebRTCVoiceHandler',
    'handle_webrtc_call',
    'WebRTCSignalingServer',
    'WebRTCSession',
    'signaling_server',
    'get_ice_servers',
    'get_rtc_configuration'
]

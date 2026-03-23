"""
ICE (Interactive Connectivity Establishment) Configuration

STUN servers: Help discover public IP addresses
TURN servers: Relay traffic when direct connection fails (firewall/NAT)
"""

import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def get_ice_servers() -> List[Dict[str, Any]]:
    """
    Get ICE server configuration for WebRTC connections.

    Returns list of STUN/TURN servers for peer connection establishment.
    """
    ice_servers = []

    # Public STUN servers (free, for NAT traversal)
    ice_servers.extend([
        {"urls": "stun:stun.l.google.com:19302"},
        {"urls": "stun:stun1.l.google.com:19302"},
        {"urls": "stun:stun2.l.google.com:19302"},
        {"urls": "stun:stun3.l.google.com:19302"},
        {"urls": "stun:stun4.l.google.com:19302"},
    ])

    # Custom TURN server (for relay when direct connection fails)
    # Configure these in environment variables for production
    turn_url = os.getenv("TURN_SERVER_URL")
    turn_username = os.getenv("TURN_USERNAME")
    turn_credential = os.getenv("TURN_CREDENTIAL")

    if turn_url and turn_username and turn_credential:
        ice_servers.append({
            "urls": turn_url,
            "username": turn_username,
            "credential": turn_credential
        })
        logger.info(f"[ICE] TURN server configured: {turn_url}")
    else:
        logger.warning("[ICE] No TURN server configured - WebRTC may fail behind strict NAT/firewall")

        # Add free TURN servers as fallback (limited bandwidth, for testing only)
        # In production, use your own TURN server (e.g., coturn) or a service like Twilio TURN
        ice_servers.append({
            "urls": "turn:openrelay.metered.ca:80",
            "username": "openrelayproject",
            "credential": "openrelayproject"
        })
        ice_servers.append({
            "urls": "turn:openrelay.metered.ca:443",
            "username": "openrelayproject",
            "credential": "openrelayproject"
        })

    return ice_servers


def get_rtc_configuration() -> Dict[str, Any]:
    """
    Get full RTCPeerConnection configuration.
    """
    return {
        "iceServers": get_ice_servers(),
        "iceTransportPolicy": "all",  # Use both STUN and TURN
        "bundlePolicy": "max-bundle",  # Bundle all media into single connection
        "rtcpMuxPolicy": "require",  # Multiplex RTP and RTCP
        "iceCandidatePoolSize": 10,  # Pre-gather candidates for faster connection
    }

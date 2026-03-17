"""
WebRTC Signaling Server

Handles WebRTC session establishment:
1. SDP (Session Description Protocol) offer/answer exchange
2. ICE candidate exchange
3. Call state management

The actual audio flows peer-to-peer after signaling is complete.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, Any, Callable, Awaitable
from fastapi import WebSocket, WebSocketDisconnect

from .ice_config import get_rtc_configuration

logger = logging.getLogger(__name__)


class WebRTCSession:
    """Represents an active WebRTC call session"""

    def __init__(self, session_id: str, assistant_id: str, user_id: str):
        self.session_id = session_id
        self.assistant_id = assistant_id
        self.user_id = user_id
        self.created_at = datetime.now(timezone.utc)

        # WebSocket for signaling
        self.websocket: Optional[WebSocket] = None

        # Call state
        self.state = "initializing"  # initializing, connecting, connected, disconnected
        self.local_description: Optional[Dict] = None
        self.remote_description: Optional[Dict] = None
        self.ice_candidates: list = []

        # Audio processing callback
        self.on_audio_data: Optional[Callable[[bytes], Awaitable[None]]] = None

        # Barge-in callback (client detected user speaking during AI speech)
        self.on_barge_in: Optional[Callable[[], Awaitable[None]]] = None

        # Playback-complete callback (client finished playing all buffered audio)
        self.on_playback_complete: Optional[Callable[[], Awaitable[None]]] = None

        # Metrics
        self.connection_start_time: Optional[float] = None
        self.audio_packets_received = 0
        self.audio_packets_sent = 0


class WebRTCSignalingServer:
    """
    WebRTC Signaling Server for establishing peer connections.

    Flow:
    1. Client connects via WebSocket
    2. Server sends ICE configuration
    3. Client creates offer, sends to server
    4. Server creates answer, sends to client
    5. ICE candidates are exchanged
    6. WebRTC connection established
    7. Audio flows directly (or via server for AI processing)
    """

    def __init__(self):
        self.sessions: Dict[str, WebRTCSession] = {}
        self.active_connections: Dict[str, WebSocket] = {}
        logger.info("[WEBRTC-SIGNALING] Server initialized")

    async def handle_connection(
        self,
        websocket: WebSocket,
        assistant_id: str,
        user_id: str,
        on_session_ready: Optional[Callable[[WebRTCSession], Awaitable[None]]] = None
    ):
        """
        Handle WebRTC signaling connection.

        Args:
            websocket: FastAPI WebSocket connection
            assistant_id: AI assistant ID
            user_id: User making the call
            on_session_ready: Callback when WebRTC session is established
        """
        # Accept only if not already accepted (route handler may accept early
        # to prevent browser timeout during DB lookups).
        if websocket.client_state.name != "CONNECTED":
            await websocket.accept()

        session_id = str(uuid.uuid4())
        session = WebRTCSession(session_id, assistant_id, user_id)
        session.websocket = websocket
        self.sessions[session_id] = session
        self.active_connections[session_id] = websocket

        logger.info(f"[WEBRTC-SIGNALING] New connection: session={session_id}, assistant={assistant_id}")

        try:
            # Send initial configuration
            await self._send_config(websocket, session_id)

            # Handle signaling messages
            await self._message_loop(session, on_session_ready)

        except WebSocketDisconnect:
            logger.info(f"[WEBRTC-SIGNALING] Client disconnected: {session_id}")
        except Exception as e:
            logger.error(f"[WEBRTC-SIGNALING] Error: {e}", exc_info=True)
        finally:
            await self._cleanup_session(session_id)

    async def _send_config(self, websocket: WebSocket, session_id: str):
        """Send configuration to client (WebSocket audio mode - no SDP/ICE needed)"""
        config = {
            "type": "config",
            "sessionId": session_id,
            "mode": "websocket-audio",
            "audioConstraints": {
                "echoCancellation": True,
                "noiseSuppression": True,
                "autoGainControl": True,
                "sampleRate": 16000,
                "channelCount": 1,
            }
        }
        await websocket.send_json(config)
        logger.info(f"[WEBRTC-SIGNALING] Sent config to {session_id} (websocket-audio mode)")

    async def _message_loop(
        self,
        session: WebRTCSession,
        on_session_ready: Optional[Callable[[WebRTCSession], Awaitable[None]]]
    ):
        """Process signaling messages"""
        while True:
            try:
                message = await session.websocket.receive_json()
                msg_type = message.get("type")

                if msg_type == "offer":
                    await self._handle_offer(session, message)

                elif msg_type == "answer":
                    await self._handle_answer(session, message)

                elif msg_type == "ice-candidate":
                    await self._handle_ice_candidate(session, message)

                elif msg_type == "ready":
                    # Browser client has mic access and is ready to stream audio
                    session.state = "connected"
                    session.connection_start_time = asyncio.get_event_loop().time()
                    logger.info(f"[WEBRTC-SIGNALING] Session {session.session_id} ready (websocket-audio mode)")

                    if on_session_ready:
                        await on_session_ready(session)

                elif msg_type == "connected":
                    # Legacy: true WebRTC connection established
                    session.state = "connected"
                    session.connection_start_time = asyncio.get_event_loop().time()
                    logger.info(f"[WEBRTC-SIGNALING] Session {session.session_id} connected!")

                    if on_session_ready:
                        await on_session_ready(session)

                elif msg_type == "audio":
                    # Audio data from client (for server-side processing)
                    await self._handle_audio(session, message)

                elif msg_type == "barge-in":
                    logger.info(f"[WEBRTC-SIGNALING] Client barge-in: {session.session_id}")
                    if session.on_barge_in:
                        await session.on_barge_in()

                elif msg_type == "playback-complete":
                    logger.info(f"[WEBRTC-SIGNALING] Client playback complete: {session.session_id}")
                    if session.on_playback_complete:
                        await session.on_playback_complete()

                elif msg_type == "hangup":
                    logger.info(f"[WEBRTC-SIGNALING] Client hangup: {session.session_id}")
                    break

                elif msg_type == "ping":
                    await session.websocket.send_json({"type": "pong"})

                else:
                    logger.warning(f"[WEBRTC-SIGNALING] Unknown message type: {msg_type}")

            except WebSocketDisconnect:
                raise
            except json.JSONDecodeError:
                logger.warning("[WEBRTC-SIGNALING] Invalid JSON received")
            except Exception as e:
                logger.error(f"[WEBRTC-SIGNALING] Message handling error: {e}")

    async def _handle_offer(self, session: WebRTCSession, message: Dict):
        """Handle SDP offer from client"""
        session.remote_description = message.get("sdp")
        session.state = "connecting"
        logger.info(f"[WEBRTC-SIGNALING] Received offer for {session.session_id}")

        # In a full implementation, we would:
        # 1. Create a server-side RTCPeerConnection (using aiortc)
        # 2. Set the remote description
        # 3. Create and send an answer
        # 4. Handle audio tracks for AI processing

        # For now, send acknowledgment
        await session.websocket.send_json({
            "type": "offer-received",
            "sessionId": session.session_id
        })

    async def _handle_answer(self, session: WebRTCSession, message: Dict):
        """Handle SDP answer (if server sent offer)"""
        session.local_description = message.get("sdp")
        logger.info(f"[WEBRTC-SIGNALING] Received answer for {session.session_id}")

    async def _handle_ice_candidate(self, session: WebRTCSession, message: Dict):
        """Handle ICE candidate from client"""
        candidate = message.get("candidate")
        if candidate:
            session.ice_candidates.append(candidate)
            logger.debug(f"[WEBRTC-SIGNALING] Received ICE candidate for {session.session_id}")

    async def _handle_audio(self, session: WebRTCSession, message: Dict):
        """Handle audio data sent via data channel"""
        audio_data = message.get("data")
        if audio_data and session.on_audio_data:
            session.audio_packets_received += 1
            # Decode base64 audio if necessary
            import base64
            audio_bytes = base64.b64decode(audio_data)
            await session.on_audio_data(audio_bytes)

    async def send_audio_to_client(self, session_id: str, audio_bytes: bytes):
        """Send audio data to client (PCM 16-bit 16kHz)"""
        session = self.sessions.get(session_id)
        if session and session.websocket:
            try:
                import base64
                await session.websocket.send_json({
                    "type": "audio",
                    "format": "pcm_s16le_24k",
                    "data": base64.b64encode(audio_bytes).decode()
                })
                session.audio_packets_sent += 1
            except Exception as e:
                logger.warning(f"[WEBRTC-SIGNALING] Failed to send audio to {session_id}: {e}")

    async def send_transcript_to_client(
        self, session_id: str, text: str, is_final: bool, speaker: str = "user"
    ):
        """Send real-time transcript update to client"""
        session = self.sessions.get(session_id)
        if session and session.websocket:
            try:
                await session.websocket.send_json({
                    "type": "transcript",
                    "speaker": speaker,
                    "text": text,
                    "isFinal": is_final
                })
            except Exception as e:
                logger.warning(f"[WEBRTC-SIGNALING] Failed to send transcript to {session_id}: {e}")

    async def send_call_state_to_client(self, session_id: str, state: str):
        """Send call state update to client (connecting, listening, ai-speaking)"""
        session = self.sessions.get(session_id)
        if session and session.websocket:
            try:
                await session.websocket.send_json({
                    "type": "call-state",
                    "state": state,
                    "sessionId": session_id
                })
            except Exception as e:
                logger.warning(f"[WEBRTC-SIGNALING] Failed to send state to {session_id}: {e}")

    async def _cleanup_session(self, session_id: str):
        """Clean up session resources"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.state = "disconnected"

            # Log metrics
            if session.connection_start_time:
                duration = asyncio.get_event_loop().time() - session.connection_start_time
                logger.info(
                    f"[WEBRTC-SIGNALING] Session {session_id} ended - "
                    f"Duration: {duration:.1f}s, "
                    f"Audio RX: {session.audio_packets_received}, "
                    f"Audio TX: {session.audio_packets_sent}"
                )

            del self.sessions[session_id]

        if session_id in self.active_connections:
            del self.active_connections[session_id]

    def get_session(self, session_id: str) -> Optional[WebRTCSession]:
        """Get session by ID"""
        return self.sessions.get(session_id)

    def get_active_session_count(self) -> int:
        """Get count of active sessions"""
        return len(self.sessions)


# Singleton instance
signaling_server = WebRTCSignalingServer()

"""
Mark Event Metadata Management
Tracks Twilio mark events for accurate audio playback monitoring and interruption handling
Based on Bolna's architecture
"""
import copy
from app.voice_pipeline.helpers.logger_config import configure_logger

logger = configure_logger(__name__)


class MarkEventMetaData:
    """
    Manages metadata for Twilio mark events

    Mark events are sent before/after audio chunks to track:
    - What audio is currently being played
    - What text the user has actually heard
    - How to sync conversation history on interruptions
    """

    def __init__(self):
        self.mark_event_meta_data = {}
        self.previous_mark_event_meta_data = {}
        self.counter = 0

    def update_data(self, mark_id: str, value: dict):
        """
        Store metadata about a mark event

        Args:
            mark_id: UUID of the mark event
            value: Dictionary containing mark metadata
        """
        # Only set counter if caller didn't provide one
        if 'counter' not in value:
            value['counter'] = self.counter
            self.counter += 1
        self.mark_event_meta_data[mark_id] = value
        logger.debug(f"[MARK_META] Stored mark {mark_id}: {value}")

    def fetch_data(self, mark_id: str) -> dict:
        """
        Retrieve and remove mark data when Twilio sends mark event

        Args:
            mark_id: UUID of the mark event

        Returns:
            Dictionary containing mark metadata, or empty dict if not found
        """
        data = self.mark_event_meta_data.pop(mark_id, {})
        if data:
            logger.debug(f"[MARK_META] Fetched mark {mark_id}: {data}")
        else:
            logger.warning(f"[MARK_META] Mark {mark_id} not found in metadata")
        return data

    def clear_data(self):
        """
        Clear all marks and save them to previous for history sync
        Called during interruptions to preserve what was being said
        """
        logger.info(f"[MARK_META] Clearing mark metadata dict (had {len(self.mark_event_meta_data)} entries)")
        self.counter = 0
        self.previous_mark_event_meta_data = copy.deepcopy(self.mark_event_meta_data)
        self.mark_event_meta_data = {}

    def fetch_cleared_mark_event_data(self) -> dict:
        """
        Retrieve all cleared marks after interruption
        Used to sync conversation history with what was actually heard

        Returns:
            Dictionary of cleared mark events
        """
        return self.previous_mark_event_meta_data

    def get_pending_marks_count(self) -> int:
        """Get count of marks waiting for acknowledgment"""
        return len(self.mark_event_meta_data)

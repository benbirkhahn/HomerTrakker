#!/usr/bin/env python3
"""
Homer Timing Logger
Tracks and analyzes clip arrival timing patterns for HomerTrakker
"""

import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path
import threading
from typing import Dict, Optional

class HomerTimingLogger:
    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent
        self.log_dir = self.base_dir / "logs" / "timing"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('homer_timing')
        
        # In-memory cache of active homer events
        self._active_events: Dict[str, dict] = {}
        self._lock = threading.Lock()
        
        # Ensure today's log file exists
        self._current_date = None
        self._ensure_log_file()
    
    def _ensure_log_file(self):
        """Ensures the log file for today exists and rotates if needed"""
        today = datetime.now().strftime('%Y-%m-%d')
        if today != self._current_date:
            self._current_date = today
            self.log_file = self.log_dir / f"clip_timing_{today}.json"
            if not self.log_file.exists():
                self.log_file.write_text('[]')
    
    def _load_log_data(self) -> list:
        """Load the current log file data"""
        try:
            return json.loads(self.log_file.read_text())
        except Exception as e:
            self.logger.error(f"Error loading log data: {e}")
            return []
    
    def _save_log_data(self, data: list):
        """Save data to the log file"""
        try:
            with open(self.log_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving log data: {e}")
    
    def record_homer_event(self, game_pk: str, at_bat_index: int, event_time: Optional[str] = None):
        """Record a new home run event"""
        event_id = f"{game_pk}_{at_bat_index}"
        event_time = event_time or datetime.utcnow().isoformat()
        
        with self._lock:
            self._active_events[event_id] = {
                'event_id': event_id,
                'game_pk': game_pk,
                'at_bat_index': at_bat_index,
                'event_time': event_time,
                'broadcast_clip_time': None,
                'animated_clip_time': None,
                'completed': False
            }
    
    def record_clip_arrival(self, game_pk: str, at_bat_index: int, clip_type: str):
        """Record when a clip becomes available"""
        event_id = f"{game_pk}_{at_bat_index}"
        arrival_time = datetime.utcnow().isoformat()
        
        with self._lock:
            if event_id not in self._active_events:
                self.logger.warning(f"Recording clip for unknown event: {event_id}")
                return
            
            event = self._active_events[event_id]
            if clip_type == 'broadcast':
                event['broadcast_clip_time'] = arrival_time
            elif clip_type == 'animated':
                event['animated_clip_time'] = arrival_time
            
            # If both clips are present, mark as completed and save
            if event['broadcast_clip_time'] and event['animated_clip_time']:
                event['completed'] = True
                self._save_event(event)
                del self._active_events[event_id]
    
    def record_timeout(self, game_pk: str, at_bat_index: int):
        """Record when an event times out waiting for both clips"""
        event_id = f"{game_pk}_{at_bat_index}"
        timeout_time = datetime.utcnow().isoformat()
        
        with self._lock:
            if event_id not in self._active_events:
                return
            
            event = self._active_events[event_id]
            event['timeout_time'] = timeout_time
            event['completed'] = True
            self._save_event(event)
            del self._active_events[event_id]
    
    def _save_event(self, event: dict):
        """Save a completed event to the log file"""
        self._ensure_log_file()
        data = self._load_log_data()
        data.append(event)
        self._save_log_data(data)
    
    def get_timing_stats(self, days: int = 7) -> dict:
        """
        Analyze timing statistics for recent events
        Returns dict with timing patterns and statistics
        """
        stats = {
            'total_events': 0,
            'both_clips_received': 0,
            'broadcast_only': 0,
            'avg_broadcast_delay': 0,
            'avg_animated_delay': 0,
            'avg_total_delay': 0
        }
        
        # Implementation of stats calculation
        # This will be expanded based on actual usage patterns
        return stats

# Global instance for easy access
timing_logger = HomerTimingLogger()
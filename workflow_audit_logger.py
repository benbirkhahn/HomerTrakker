#!/usr/bin/env python3
"""
Workflow Audit Logger
Tracks each HR through the entire pipeline: detection → enrichment → download → compilation → upload
Provides structured JSON logging for debugging missing/failed uploads.

Usage:
    from workflow_audit_logger import WorkflowAuditLogger
    
    logger = WorkflowAuditLogger()
    
    # Start tracking an HR detection
    logger.log_detection(game_pk=776135009, batter="Aaron Judge", 
                        game="Yankees @ Red Sox", inning=3)
    
    # Log each stage
    logger.log_enrichment(game_pk, success=True, ev=102.5, la=28, distance=419)
    logger.log_clip_download(game_pk, clip_type="broadcast", success=True, filename="broadcast.mp4")
    logger.log_compilation(game_pk, success=False, error="Animated clip missing")
    logger.log_upload(game_pk, success=True, video_id="abcd1234")
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import threading

BASE_DIR = Path(__file__).resolve().parent


class WorkflowAuditLogger:
    """Structured audit logging for the entire HR pipeline."""
    
    def __init__(self):
        self.audit_dir = BASE_DIR / "logs" / "audit"
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        
        # In-memory cache of current workflow run
        self._current_run = None
        self._homers = {}  # gamePk -> HR details
    
    def _get_today_file(self):
        """Get today's audit log file path."""
        today = datetime.now().strftime('%Y-%m-%d')
        return self.audit_dir / f"workflow_{today}.json"
    
    def _load_today_audit(self) -> List[Dict]:
        """Load today's audit log."""
        audit_file = self._get_today_file()
        if audit_file.exists():
            try:
                return json.loads(audit_file.read_text())
            except Exception as e:
                print(f"⚠️  Error loading audit log: {e}")
        return []
    
    def _save_today_audit(self, data: List[Dict]):
        """Save today's audit log."""
        audit_file = self._get_today_file()
        try:
            with open(audit_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️  Error saving audit log: {e}")
    
    def new_poller_run(self, run_id: Optional[str] = None) -> str:
        """
        Mark the start of a new poller execution.
        Returns the run_id for tracking.
        """
        run_id = run_id or datetime.now().isoformat()
        
        with self._lock:
            self._current_run = {
                "run_id": run_id,
                "timestamp": datetime.now().isoformat(),
                "homers_detected": 0,
                "homers": {}
            }
            self._homers = {}
        
        return run_id
    
    def log_detection(self, game_pk: int, batter: str, game: str, 
                     inning: int, inning_half: str = "top", 
                     post_file: Optional[str] = None):
        """Log HR detection (start of pipeline)."""
        if not self._current_run:
            self.new_poller_run()
        
        with self._lock:
            homer_key = str(game_pk)
            self._homers[homer_key] = {
                "game_pk": game_pk,
                "batter": batter,
                "game": game,
                "inning": f"{inning_half} {inning}",
                "post_file": post_file,
                "detected_at": datetime.now().isoformat(),
                "stages": {
                    "detection": {
                        "status": "success",
                        "timestamp": datetime.now().isoformat(),
                        "details": {}
                    }
                }
            }
            self._current_run["homers_detected"] += 1
    
    def log_enrichment(self, game_pk: int, success: bool, 
                      ev: Optional[float] = None, la: Optional[float] = None,
                      distance: Optional[int] = None, error: Optional[str] = None):
        """Log Statcast enrichment stage."""
        homer_key = str(game_pk)
        if homer_key not in self._homers:
            return
        
        with self._lock:
            stage_data = {
                "status": "success" if success else "failed",
                "timestamp": datetime.now().isoformat(),
                "details": {}
            }
            
            if success:
                stage_data["details"] = {
                    "exit_velocity": ev,
                    "launch_angle": la,
                    "distance_ft": distance
                }
            else:
                stage_data["error"] = error or "Unknown error"
            
            self._homers[homer_key]["stages"]["enrichment"] = stage_data
    
    def log_clip_download(self, game_pk: int, clip_type: str, success: bool,
                         filename: Optional[str] = None, size_mb: Optional[float] = None,
                         error: Optional[str] = None, duration_sec: Optional[float] = None):
        """
        Log clip download (broadcast or animated).
        clip_type: "broadcast" or "animated"
        """
        homer_key = str(game_pk)
        if homer_key not in self._homers:
            return
        
        stage_key = f"{clip_type}_clip"
        
        with self._lock:
            stage_data = {
                "status": "success" if success else "failed",
                "timestamp": datetime.now().isoformat(),
                "details": {}
            }
            
            if success:
                stage_data["details"] = {
                    "filename": filename,
                    "size_mb": size_mb,
                    "duration_sec": duration_sec
                }
            else:
                stage_data["error"] = error or "Download failed"
            
            self._homers[homer_key]["stages"][stage_key] = stage_data
    
    def log_compilation(self, game_pk: int, success: bool,
                       filename: Optional[str] = None, duration_sec: Optional[float] = None,
                       resolution: Optional[str] = None, error: Optional[str] = None):
        """Log video compilation stage."""
        homer_key = str(game_pk)
        if homer_key not in self._homers:
            return
        
        with self._lock:
            stage_data = {
                "status": "success" if success else "failed",
                "timestamp": datetime.now().isoformat(),
                "details": {}
            }
            
            if success:
                stage_data["details"] = {
                    "filename": filename,
                    "duration_sec": duration_sec,
                    "resolution": resolution or "9:16"
                }
            else:
                stage_data["error"] = error or "Compilation failed"
            
            self._homers[homer_key]["stages"]["compilation"] = stage_data
    
    def log_upload(self, game_pk: int, success: bool,
                  video_id: Optional[str] = None, url: Optional[str] = None,
                  error: Optional[str] = None):
        """Log YouTube upload stage."""
        homer_key = str(game_pk)
        if homer_key not in self._homers:
            return
        
        with self._lock:
            stage_data = {
                "status": "success" if success else "failed",
                "timestamp": datetime.now().isoformat(),
                "details": {}
            }
            
            if success:
                stage_data["details"] = {
                    "video_id": video_id,
                    "url": url
                }
            else:
                stage_data["error"] = error or "Upload failed"
            
            self._homers[homer_key]["stages"]["upload"] = stage_data
    
    def log_skip(self, game_pk: int, reason: str):
        """Log when an HR is skipped (e.g., duplicate, missing clips)."""
        homer_key = str(game_pk)
        if homer_key not in self._homers:
            return
        
        with self._lock:
            self._homers[homer_key]["skipped"] = True
            self._homers[homer_key]["skip_reason"] = reason
    
    def save_current_run(self):
        """Save the current poller run to disk."""
        if not self._current_run:
            return
        
        with self._lock:
            self._current_run["homers"] = list(self._homers.values())
            
            # Load existing runs for today
            today_runs = self._load_today_audit()
            
            # Append current run
            today_runs.append(self._current_run)
            
            # Save back
            self._save_today_audit(today_runs)
            
            print(f"📝 Saved workflow audit: {self._current_run['run_id']}")
    
    def get_today_summary(self) -> Dict[str, Any]:
        """Get summary of today's workflow runs."""
        runs = self._load_today_audit()
        
        summary = {
            "total_runs": len(runs),
            "total_homers_detected": 0,
            "total_uploaded": 0,
            "total_failed": 0,
            "total_skipped": 0,
            "runs": []
        }
        
        for run in runs:
            run_summary = {
                "run_id": run.get("run_id"),
                "timestamp": run.get("timestamp"),
                "detected": run.get("homers_detected", 0),
                "uploaded": 0,
                "failed": 0,
                "skipped": 0
            }
            
            for homer in run.get("homers", []):
                summary["total_homers_detected"] += 1
                
                if homer.get("skipped"):
                    summary["total_skipped"] += 1
                    run_summary["skipped"] += 1
                elif homer.get("stages", {}).get("upload", {}).get("status") == "success":
                    summary["total_uploaded"] += 1
                    run_summary["uploaded"] += 1
                else:
                    summary["total_failed"] += 1
                    run_summary["failed"] += 1
            
            summary["runs"].append(run_summary)
        
        return summary
    
    def get_failed_homers(self, limit: int = 20) -> List[Dict]:
        """Get list of failed HRs for manual retry."""
        runs = self._load_today_audit()
        failed = []
        
        for run in runs:
            for homer in run.get("homers", []):
                if homer.get("skipped"):
                    continue
                
                # Check which stage failed
                for stage_name, stage_data in homer.get("stages", {}).items():
                    if stage_data.get("status") == "failed":
                        failed.append({
                            "game_pk": homer.get("game_pk"),
                            "batter": homer.get("batter"),
                            "game": homer.get("game"),
                            "failed_stage": stage_name,
                            "error": stage_data.get("error"),
                            "detected_at": homer.get("detected_at"),
                            "run_id": run.get("run_id")
                        })
                        break
        
        return failed[:limit]


# Global instance
workflow_logger = WorkflowAuditLogger()

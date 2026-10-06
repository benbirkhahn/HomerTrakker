#!/usr/bin/env python3
"""
N8N Audit Logger
Simple helper to read/write audit logs from N8N workflow executions.
N8N nodes write JSON updates; this reads them for the dashboard.

Usage from dashboard:
    logger = N8NAuditLogger()
    runs = logger.get_today_runs()
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

BASE_DIR = Path(__file__).resolve().parent


class N8NAuditLogger:
    """Reads/writes audit logs for N8N workflow executions."""
    
    def __init__(self):
        self.audit_dir = BASE_DIR / "logs" / "audit"
        self.audit_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_today_file(self) -> Path:
        """Get today's audit log file."""
        today = datetime.now().strftime('%Y-%m-%d')
        return self.audit_dir / f"n8n_audit_{today}.json"
    
    def get_today_runs(self) -> List[Dict[str, Any]]:
        """Load all runs from today's audit log."""
        audit_file = self._get_today_file()
        if not audit_file.exists():
            return []
        
        try:
            return json.loads(audit_file.read_text())
        except Exception as e:
            print(f"⚠️  Error loading audit: {e}")
            return []
    
    def get_current_run(self) -> Optional[Dict[str, Any]]:
        """Get the most recent (likely in-progress) run."""
        runs = self.get_today_runs()
        return runs[-1] if runs else None
    
    def _save_runs(self, runs: List[Dict]):
        """Save runs to today's audit file."""
        audit_file = self._get_today_file()
        try:
            with open(audit_file, 'w') as f:
                json.dump(runs, f, indent=2)
        except Exception as e:
            print(f"⚠️  Error saving audit: {e}")
    
    def start_execution(self, execution_id: str) -> Dict:
        """Create a new execution run entry."""
        run = {
            "execution_id": execution_id,
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "status": "running",
            "nodes": {},
            "homers": []
        }
        
        runs = self.get_today_runs()
        runs.append(run)
        self._save_runs(runs)
        
        return run
    
    def log_node_start(self, execution_id: str, node_name: str, details: Optional[Dict] = None):
        """Log when a node starts executing."""
        runs = self.get_today_runs()
        
        for run in runs:
            if run["execution_id"] == execution_id:
                run["nodes"][node_name] = {
                    "status": "running",
                    "started_at": datetime.now().isoformat(),
                    "completed_at": None,
                    "details": details or {}
                }
                break
        
        self._save_runs(runs)
    
    def log_node_complete(self, execution_id: str, node_name: str, 
                         status: str = "success", details: Optional[Dict] = None):
        """Log when a node completes."""
        runs = self.get_today_runs()
        
        for run in runs:
            if run["execution_id"] == execution_id:
                if node_name not in run["nodes"]:
                    run["nodes"][node_name] = {
                        "status": status,
                        "started_at": datetime.now().isoformat(),
                        "completed_at": datetime.now().isoformat(),
                        "details": {}
                    }
                else:
                    run["nodes"][node_name]["status"] = status
                    run["nodes"][node_name]["completed_at"] = datetime.now().isoformat()
                
                if details:
                    run["nodes"][node_name]["details"] = details
                break
        
        self._save_runs(runs)
    
    def log_homers_detected(self, execution_id: str, homers: List[Dict]):
        """Log detected HRs (called after detection node)."""
        runs = self.get_today_runs()
        
        for run in runs:
            if run["execution_id"] == execution_id:
                for homer in homers:
                    run["homers"].append({
                        "game_pk": homer.get("game_pk"),
                        "batter": homer.get("batter", "Unknown"),
                        "game": homer.get("game", "Unknown"),
                        "inning": homer.get("inning", "?"),
                        "detected_at": datetime.now().isoformat(),
                        "stages": {
                            "detection": {"status": "✓", "timestamp": datetime.now().isoformat()},
                            "content": {"status": "—"},
                            "download_diamond": {"status": "—"},
                            "download_animated": {"status": "—"},
                            "compile": {"status": "—"},
                            "upload": {"status": "—"}
                        }
                    })
                break
        
        self._save_runs(runs)
    
    def log_homer_stage(self, execution_id: str, game_pk: int, stage: str, 
                       status: str, error: Optional[str] = None):
        """Log progress of a specific HR through a stage."""
        runs = self.get_today_runs()
        
        for run in runs:
            if run["execution_id"] == execution_id:
                for homer in run["homers"]:
                    if homer["game_pk"] == game_pk:
                        if stage in homer["stages"]:
                            icon = "✓" if status == "success" else ("✗" if status == "failed" else "...")
                            homer["stages"][stage] = {
                                "status": icon,
                                "timestamp": datetime.now().isoformat(),
                                "error": error
                            }
                        break
                break
        
        self._save_runs(runs)
    
    def end_execution(self, execution_id: str, status: str = "completed"):
        """Mark an execution as complete."""
        runs = self.get_today_runs()
        
        for run in runs:
            if run["execution_id"] == execution_id:
                run["status"] = status
                run["completed_at"] = datetime.now().isoformat()
                break
        
        self._save_runs(runs)
    
    def get_summary(self, execution_id: str) -> Dict:
        """Get summary stats for an execution."""
        runs = self.get_today_runs()
        
        for run in runs:
            if run["execution_id"] == execution_id:
                homers = run["homers"]
                total = len(homers)
                uploaded = sum(1 for h in homers if h["stages"].get("upload", {}).get("status") == "✓")
                failed = sum(1 for h in homers if any(
                    s.get("status") == "✗" for s in h["stages"].values()
                ))
                pending = total - uploaded - failed
                
                nodes = run["nodes"]
                nodes_success = sum(1 for n in nodes.values() if n["status"] == "success")
                nodes_failed = sum(1 for n in nodes.values() if n["status"] == "failed")
                
                return {
                    "total_homers": total,
                    "uploaded": uploaded,
                    "failed": failed,
                    "pending": pending,
                    "nodes_total": len(nodes),
                    "nodes_success": nodes_success,
                    "nodes_failed": nodes_failed
                }
        
        return {}


# Global instance
n8n_logger = N8NAuditLogger()

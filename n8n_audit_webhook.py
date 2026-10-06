#!/usr/bin/env python3
"""
N8N Audit Webhook Server
Receives HTTP POST requests from N8N workflow nodes and logs to audit files.

This solves the "fs module disallowed" issue in N8N by accepting HTTP webhooks.

Run: python3 n8n_audit_webhook.py
If N8N runs on another host, set the webhook URL to the reachable address, for example:
  http://YOUR_WEBHOOK_HOST:9000/audit
"""

from flask import Flask, request, jsonify
from pathlib import Path
from datetime import datetime
import json
import os
from threading import Lock

app = Flask(__name__)
audit_lock = Lock()

BASE_DIR = Path(__file__).resolve().parent


def get_audit_file():
    """Get today's audit log file path."""
    today = datetime.now().strftime('%Y-%m-%d')
    audit_dir = BASE_DIR / "logs" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    return audit_dir / f"n8n_audit_{today}.json"


def read_audit():
    """Read current audit log."""
    audit_file = get_audit_file()
    if audit_file.exists():
        try:
            return json.loads(audit_file.read_text())
        except Exception as e:
            print(f"⚠️  Error reading audit: {e}")
    return []


def write_audit(data):
    """Write audit log."""
    audit_file = get_audit_file()
    try:
        with open(audit_file, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"⚠️  Error writing audit: {e}")
        return False


@app.route('/audit', methods=['POST'])
def log_audit():
    """
    Receive audit event from N8N.
    
    Expected JSON:
    {
        "execution_id": "...",
        "action": "start|detection|content|downloads|compile|upload|end",
        "homers": [...],
        "details": {...}
    }
    """
    try:
        data = request.json or {}
        execution_id = data.get('execution_id')
        action = data.get('action')
        
        if not execution_id or not action:
            return jsonify({"error": "Missing execution_id or action"}), 400
        
        with audit_lock:
            runs = read_audit()
            
            if action == 'start':
                # New execution
                run = {
                    "execution_id": execution_id,
                    "started_at": datetime.now().isoformat(),
                    "status": "running",
                    "nodes": {},
                    "homers": []
                }
                runs.append(run)
            else:
                # Update existing execution
                run = None
                for r in runs:
                    if r["execution_id"] == execution_id:
                        run = r
                        break
                
                if not run:
                    return jsonify({"error": "Execution not found"}), 404
                
                if action == 'detection':
                    # Log detected HRs
                    run["nodes"]["06_Extract_HR_Plays"] = {
                        "status": "success",
                        "completed_at": datetime.now().isoformat(),
                        "details": {"hrs_found": len(data.get('homers', []))}
                    }
                    for homer in data.get('homers', []):
                        run["homers"].append({
                            "game_pk": homer.get('gamePk') or homer.get('game_pk'),
                            "batter": homer.get('batter', 'Unknown'),
                            "game": homer.get('game', 'Unknown'),
                            "inning": homer.get('inning', '?'),
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
                
                elif action == 'content':
                    # Mark content found
                    run["nodes"]["08_Select_Clips"] = {
                        "status": "success",
                        "completed_at": datetime.now().isoformat(),
                        "details": {"clips_found": len(data.get('homers', []))}
                    }
                    for homer_id in data.get('homers', []):
                        for homer in run["homers"]:
                            if homer.get("game_pk") == homer_id:
                                homer["stages"]["content"] = {
                                    "status": "✓",
                                    "timestamp": datetime.now().isoformat()
                                }
                
                elif action == 'downloads':
                    # Mark downloads complete
                    run["nodes"]["13_Download_Diamond"] = {
                        "status": "success",
                        "completed_at": datetime.now().isoformat()
                    }
                    run["nodes"]["15_Download_Animated"] = {
                        "status": "success",
                        "completed_at": datetime.now().isoformat()
                    }
                    for homer_id in data.get('homers', []):
                        for homer in run["homers"]:
                            if homer.get("game_pk") == homer_id:
                                if data.get('has_broadcast'):
                                    homer["stages"]["download_diamond"] = {
                                        "status": "✓",
                                        "timestamp": datetime.now().isoformat()
                                    }
                                if data.get('has_animated'):
                                    homer["stages"]["download_animated"] = {
                                        "status": "✓",
                                        "timestamp": datetime.now().isoformat()
                                    }
                
                elif action == 'compile':
                    # Mark compilation complete
                    run["nodes"]["17_Compile_Shorts"] = {
                        "status": "success",
                        "completed_at": datetime.now().isoformat()
                    }
                    for homer_id in data.get('homers', []):
                        for homer in run["homers"]:
                            if homer.get("game_pk") == homer_id:
                                homer["stages"]["compile"] = {
                                    "status": "✓",
                                    "timestamp": datetime.now().isoformat()
                                }
                
                elif action == 'upload':
                    # Mark upload complete
                    run["nodes"]["18_Upload_YouTube"] = {
                        "status": "success",
                        "completed_at": datetime.now().isoformat()
                    }
                    for homer_id in data.get('homers', []):
                        for homer in run["homers"]:
                            if homer.get("game_pk") == homer_id:
                                homer["stages"]["upload"] = {
                                    "status": "✓",
                                    "timestamp": datetime.now().isoformat()
                                }
                
                elif action == 'end':
                    # Mark execution complete
                    run["nodes"]["19_Cleanup_Media"] = {
                        "status": "success",
                        "completed_at": datetime.now().isoformat()
                    }
                    run["status"] = "completed"
                    run["completed_at"] = datetime.now().isoformat()
            
            if not write_audit(runs):
                return jsonify({"error": "Failed to write audit log"}), 500
        
        return jsonify({"status": "ok"}), 200
    
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"}), 200


if __name__ == '__main__':
    print("🚀 N8N Audit Webhook Server")
    print("   Listening on http://0.0.0.0:9000")
    print("   POST events to: http://<your-webhook-host>:9000/audit")
    print("   Set N8N env WEBHOOK_URL if N8N is remote")
    print("\nIntegration Example:")
    print("""
    From N8N JavaScript node:
    
    const response = await fetch('http://localhost:9000/audit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        execution_id: 'exec-id-here',
        action: 'detection',
        homers: [{ gamePk: 123, batter: 'Judge', ... }]
      })
    });
    """)
    print()
    
    # Create audit directory
    (BASE_DIR / "logs" / "audit").mkdir(parents=True, exist_ok=True)
    
    app.run(debug=False, host='0.0.0.0', port=9000)

# N8N Real-Time Workflow Dashboard Integration Guide

## Overview

You now have a **real-time dashboard** that shows your N8N HR pipeline execution in detail:
- Live node execution timeline
- HR progression through stages
- Failure analysis with drill-down
- Execution metrics

**Files created:**
- `n8n_audit_logger.py` → Reads/writes audit JSON files
- `n8n_workflow_dashboard.py` → Real-time Dash web UI
- `n8n_audit_snippets.py` → Copy-paste JavaScript code for N8N nodes

---

## Quick Start

### 1. Start the Dashboard
```bash
cd /data/HomerTrakker
python3 n8n_workflow_dashboard.py
```
Then visit: **http://localhost:8050**

The dashboard will:
- Auto-refresh every 3 seconds
- Show live execution progress
- Update HR cards in real-time
- Highlight failures

### 2. Add Audit Logging to Your N8N Workflow

You'll insert **JavaScript code nodes** at strategic points in your workflow to log execution state to the audit file.

#### Where to Add Nodes

Your current flow:
```
01 Cron → 02 Compute Dates → 03/03b Schedule → 02b Ensure Dirs
        → Code Extract → 05 Live Feed → 06 Extract HR Plays
        → 07 Game Content → 08 Select Clips → 09 Build Paths
        → Execute Command → 10 Ensure Dirs → 11 Make Binary → 12 Write Post
        → Merge → 13 Download Diamond → 14 Save Diamond
                → 15 Download Animated → 17 Compile
        → 18 Upload → 19 Cleanup
```

**Add auditing at these 7 checkpoints:**

1. **After "02 Compute Dates"** → Log execution start
2. **After "06 Extract New HR Plays1"** → Log HRs detected
3. **After "08 Select 4000K + Animated1"** → Log content found
4. **Before "Merge1"** (combine after downloads) → Log downloads complete
5. **After "17 Compile Shorts"** → Log compilation complete
6. **After "18 Upload to YouTube1"** → Log upload complete
7. **After "19 Cleanup Media1"** → Log execution end

---

## Step-by-Step Integration

### Step 1: Create the Audit Checkpoint Nodes

In N8N:

1. **Add Node #1 (Execution Start)**
   - Click `+` after "02 Compute Dates"
   - Select "Code" → "JavaScript"
   - Name: `00 Audit Start`
   - Copy-paste from snippets:
     ```bash
     python3 n8n_audit_snippets.py START
     ```
   - Connect: "02 Compute Dates" → "00 Audit Start" → continue to rest of flow

2. **Add Node #2 (HRs Detected)**
   - After "06 Extract New HR Plays1"
   - Name: `06b Audit HRs Detected`
   - Copy-paste: `python3 n8n_audit_snippets.py HRS_DETECTED`

3. **Add Node #3 (Content Found)**
   - After "08 Select 4000K + Animated1"
   - Name: `08b Audit Content Found`
   - Copy-paste: `python3 n8n_audit_snippets.py CONTENT_FOUND`

4. **Add Node #4 (Downloads Complete)**
   - Create a new "Code (JavaScript)" node
   - Name: `16 Audit Downloads`
   - Place it **after both download nodes merge** (before "17 Compile Shorts")
   - Copy-paste: `python3 n8n_audit_snippets.py DOWNLOADS`
   - Connect: Merge nodes → "16 Audit Downloads" → "17 Compile Shorts"

5. **Add Node #5 (Compilation Complete)**
   - After "17 Compile Shorts"
   - Name: `17b Audit Compile`
   - Copy-paste: `python3 n8n_audit_snippets.py COMPILE`

6. **Add Node #6 (Upload Complete)**
   - After "18 Upload to YouTube1"
   - Name: `18b Audit Upload`
   - Copy-paste: `python3 n8n_audit_snippets.py UPLOAD`

7. **Add Node #7 (Execution End)**
   - After "19 Cleanup Media1"
   - Name: `20 Audit End`
   - Copy-paste: `python3 n8n_audit_snippets.py END`

---

### Step 2: Test One Execution

1. Make sure the dashboard is running on `localhost:8050`
2. Trigger your N8N workflow manually (don't wait for cron)
3. Watch the dashboard update in real-time as each checkpoint executes

You should see:
- ⏳ "Running" status
- HR cards appearing with "Detect ✓" stage
- Progressively more stages completing
- Final "Completed" status with upload count

---

### Step 3: Verify Audit Log File

Check that the audit file is being created:
```bash
cat /data/HomerTrakker/logs/audit/n8n_audit_$(date +%Y-%m-%d).json | jq '.' | head -50
```

You should see JSON with:
```json
{
  "execution_id": "timestamp-based-id",
  "started_at": "2026-04-04T...",
  "status": "completed",
  "nodes": {
    "06_Extract_HR_Plays": { "status": "success", ... },
    ...
  },
  "homers": [
    {
      "game_pk": 776135009,
      "batter": "Aaron Judge",
      "stages": { ... }
    }
  ]
}
```

---

## Dashboard Features

### Summary Cards (Top)
- **Detected**: Total HRs found
- **Uploaded**: Successfully uploaded
- **Failed**: Errored at some stage
- **Pending**: In progress or skipped
- **Nodes OK**: Which N8N nodes succeeded

### Node Execution Timeline
- Horizontal bar chart showing when each node ran
- Color: 🟢 success, 🔴 failed, 🟡 in progress
- Hover to see duration

### HR Flow Sankey Diagram
- Visual funnel of HRs through each stage
- Shows dropoff at each checkpoint
- Helps identify where you're losing HRs

### HR Cards
- One card per detected HR
- Shows pipeline progress
- Badge for each stage (Detect, Content, DL Diamond, DL Anim, Compile, Upload)
- Color-coded and clickable

### Failures & Issues
- Red section at bottom
- Lists which stage each HR failed at
- Shows error message from N8N node

---

## Troubleshooting

### Dashboard shows "No execution yet"
- Make sure N8N workflow has run with audit nodes added
- Check that audit file exists: `ls /data/HomerTrakker/logs/audit/`
- If not, first audit node didn't run (check N8N logs for JavaScript errors)

### HRs detected but stuck at "Detect"
- Check "08b Audit Content Found" node ran
- Look at N8N execution logs to see if "07 Game Content" API call failed
- Might be rate-limited by MLB Stats API

### Download stages show "—" (pending)
- Downloads run in parallel, so timing matters
- Make sure "16 Audit Downloads" node is placed **after** both merge
- Check N8N logs for download errors

### All HRs show as failed
- Check N8N job logs for Python script errors
- Verify `/data/HomerTrakker/.homer.env` is set correctly
- Check file permissions on `ML_HomeRun_Posts/`

### Can't connect to dashboard on :8050
- Check if port is already in use: `lsof -i :8050`
- Kill old process: `kill -9 <PID>`
- Try different port: `python3 n8n_workflow_dashboard.py --port 8051`

---

## What's Being Tracked

### Per Execution:
- Start/end time
- Status (running / completed)
- Node execution timeline
- All HRs detected

### Per HR:
- Game PK, batter, game, inning
- Detection timestamp
- Stage progression:
  - detection ✓
  - content lookup
  - broadcast clip download
  - animated clip download
  - compilation
  - upload

### Per Node:
- Start/end time
- Status
- Details (count of items processed)
- Error messages on failure

---

## Next Steps

Once integration is working:

1. **Tune dashboard refresh rate** (currently 3 seconds)
   - Edit `dcc.Interval(interval=3000)` in `n8n_workflow_dashboard.py`
   - Faster = more live, but more browser updates

2. **Add custom failure handlers**
   - When N8N node fails, add error message to audit JSON
   - Snippets catch `try/catch` in JavaScript

3. **Export audit data**
   - Use audit JSON to build analytics (which HRs fail most? which times?)
   - Build alerts if >20% failure rate

4. **Sync with Python pipeline**
   - If you keep `homer_minute_poller.py` for backup, make it write to same audit format
   - Dashboard works for both!

---

## Files Reference

| File | Purpose |
|------|---------|
| `n8n_audit_logger.py` | Helper to read/write audit JSON |
| `n8n_workflow_dashboard.py` | Main Dash dashboard (run this) |
| `n8n_audit_snippets.py` | JavaScript snippets (copy to N8N nodes) |
| `/logs/audit/n8n_audit_YYYY-MM-DD.json` | Audit log (written by N8N nodes) |

---

## Dashboard API

If you want to integrate audit data elsewhere:

```python
from n8n_audit_logger import n8n_logger

# Get all runs from today
runs = n8n_logger.get_today_runs()

# Get current (most recent) execution
current = n8n_logger.get_current_run()

# Get summary stats
summary = n8n_logger.get_summary(execution_id)
print(f"Uploaded: {summary['uploaded']}/{summary['total_homers']}")
```

---

## Questions?

Check what's happening in real-time:
```bash
# Watch audit log being written
tail -f /data/HomerTrakker/logs/audit/n8n_audit_*.json

# Pretty-print JSON
cat /data/HomerTrakker/logs/audit/n8n_audit_$(date +%Y-%m-%d).json | jq '.[-1]' # Latest execution

# Check N8N workflow logs
# → In N8N UI: Workflow → Executions → Click a run → see logs
```

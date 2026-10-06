# Quick Reference: N8N Workflow Dashboard

## Start the Dashboard
```bash
cd /data/HomerTrakker
python3 n8n_workflow_dashboard.py
# Visit: http://localhost:8050
```

## Add Audit Logging to N8N (7 nodes)

| Node | Copy-Paste Command | Placement |
|------|-------------------|-----------|
| 1. Start | `python3 n8n_audit_snippets.py START` | After "02 Compute Dates" |
| 2. HRs Detected | `python3 n8n_audit_snippets.py HRS_DETECTED` | After "06 Extract New HR Plays1" |
| 3. Content Found | `python3 n8n_audit_snippets.py CONTENT_FOUND` | After "08 Select 4000K + Animated1" |
| 4. Downloads | `python3 n8n_audit_snippets.py DOWNLOADS` | Before "17 Compile Shorts" (after merge) |
| 5. Compile | `python3 n8n_audit_snippets.py COMPILE` | After "17 Compile Shorts" |
| 6. Upload | `python3 n8n_audit_snippets.py UPLOAD` | After "18 Upload to YouTube1" |
| 7. End | `python3 n8n_audit_snippets.py END` | After "19 Cleanup Media1" |

## Dashboard Shows
✅ Node execution timeline (when each ran, status)
✅ HR cards with stage progress
✅ Sankey diagram of HRs through pipeline
✅ Failure breakdown by stage
✅ Live updates every 3 seconds

## View Audit Log
```bash
# Today's audit
cat /data/HomerTrakker/logs/audit/n8n_audit_$(date +%Y-%m-%d).json | jq '.'

# Latest execution only
cat /data/HomerTrakker/logs/audit/n8n_audit_*.json | jq '.[-1]'
```

## Troubleshoot
- No execution? → Make sure N8N workflow ran after adding audit nodes
- HRs stuck at stage? → Check N8N job logs for errors in that node
- Port 8050 in use? → `lsof -i :8050` then `kill -9 <PID>`

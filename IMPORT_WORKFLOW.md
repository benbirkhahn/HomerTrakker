# N8N Workflow Import Instructions

## ✅ Your Workflow is Ready

File: **`hometrakker_workflow_with_audit.json`**
- **33 nodes** (26 original + 7 audit checkpoints)
- **37 KB**, fully integrated
- Ready to import into N8N

---

## 📥 How to Import

### Step 1: Open N8N UI
Go to your N8N instance (usually `http://localhost:5678` or your server)

### Step 2: Import the Workflow
1. Click **"Workflows"** in left sidebar
2. Click **"Import workflow"** (or gear icon → Import)
3. Select **`hometrakker_workflow_with_audit.json`** from your computer
4. Click **"Import"**

### Step 3: Review
N8N will load the workflow and show all 33 nodes connected correctly.

You should see:
- ✅ Original 26 nodes intact
- ✅ **7 new audit checkpoints** inserted:
  1. `00 Audit Start` (after Compute Dates)
  2. `06b Audit HRs Detected` (after Extract HRs)
  3. `08b Audit Content Found` (after Select Clips)
  4. `16 Audit Downloads` (before Compile)
  5. `17b Audit Compile` (after Compile)
  6. `18b Audit Upload` (after Upload)
  7. `20 Audit End` (after Cleanup)

### Step 4: Save & Test
1. Click **"Save"** (top right)
2. Review workflow visually (zoom out to see full flow)
3. Click **"Execute workflow"** button to test

---

## 🎯 What Happens When You Run It

As N8N executes:

1. ✅ **00 Audit Start** logs execution ID to audit file
2. ✅ HRs are detected (game APIs called)
3. ✅ **06b Audit HRs Detected** logs each HR with game details
4. ✅ Content is looked up
5. ✅ **08b Audit Content Found** marks HRs with content found
6. ✅ Videos download in parallel
7. ✅ **16 Audit Downloads** marks both broadcast & animated downloaded
8. ✅ **17b Audit Compile** marks compilation complete
9. ✅ **18b Audit Upload** marks upload complete
10. ✅ **20 Audit End** marks execution as complete

---

## 📊 View in Dashboard

**In separate terminal:**
```bash
cd /Users/benbirkhahn/HomerTrakker
python3 n8n_workflow_dashboard.py
```

**Then visit:** http://localhost:8050

The dashboard will show:
- Real-time node execution timeline
- HR cards with stage badges
- Sankey flow diagram
- Failure breakdown

---

## ✅ Checklist

- [ ] Downloaded `hometrakker_workflow_with_audit.json`
- [ ] Imported into N8N
- [ ] Saved the workflow
- [ ] Dashboard is running on :8050
- [ ] Executed workflow once to test
- [ ] Watched dashboard update in real-time
- [ ] Confirmed audit file created: `/logs/audit/n8n_audit_YYYY-MM-DD.json`

---

## 🆘 Troubleshooting

**Workflow won't import?**
- Make sure file isn't corrupted: `python3 -c "import json; json.load(open('hometrakker_workflow_with_audit.json'))"`

**Dashboard shows no execution?**
- Trigger workflow again after importing
- Check audit file: `cat /data/HomerTrakker/logs/audit/n8n_audit_$(date +%Y-%m-%d).json | jq '.[-1]'`

**Audit nodes have errors?**
- Check N8N logs for JavaScript errors in code nodes
- Verify `/data/HomerTrakker/logs/audit/` directory exists and is writable

---

## 📝 File Locations

| File | Location | Purpose |
|------|----------|---------|
| Workflow JSON | `hometrakker_workflow_with_audit.json` | Import this into N8N |
| Dashboard | `n8n_workflow_dashboard.py` | Run to view real-time updates |
| Audit Logs | `/data/HomerTrakker/logs/audit/n8n_audit_YYYY-MM-DD.json` | Written by workflow |

Done! Ready to import? 🚀

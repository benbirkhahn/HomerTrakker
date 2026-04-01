# HomerTrakker n8n Troubleshooting & Docker Setup

This document tracks solutions to issues we've encountered using n8n for our fully automated HomerTrakker workflow, specifically regarding macOS Desktop sandboxing and JavaScript node array handling.

## 1. n8n macOS App Sandboxing and File Permission Issues

### The Problem
When running the native `n8n Desktop` app on macOS, it is strictly sandboxed. This prevents it from writing files (such as `.mp4` video downloads) to arbitrary host directories, even if the directories are given 777 permissions. n8n's "Write Binary File" node silently fails or produces 0-byte corrupt files due to this underlying sandbox restriction.

### The Solution: Dockerized n8n
We migrated off the macOS desktop app to a **Dockerized n8n container**. This allows us to map specific local volumes `/Users/benbirkhahn/HomerTrakker` directly into the container as `/data/HomerTrakker` without Apple's sandbox getting in the way.

To start the reliable Docker environment, use the included `docker-compose.yml`:
```bash
cd /Users/benbirkhahn/HomerTrakker
docker compose up -d --build
```
Access the fixed n8n interface at: `http://localhost:5678`

### The "Execute Command" Workaround
Even in Docker, n8n has internal limitations on file access directories (controlled via `N8N_ENFORCEMENT_FS_FILE_ACCESS=false` but can still be stubborn with large binaries).
To safely interact with our Python pipeline, we use n8n **Execute Command** nodes to run Python and shell workflows natively inside the mapped volume.

To write text files directly, we use the following Bash structure inside an Execute Command node:
```bash
cat << 'N8N_EOF' > "/data/HomerTrakker/MLB_HomeRun_Posts/{{$json.today}}/file.txt"
{{$json.postText}}
N8N_EOF
```
*Note: We must enable `N8N_UNSAFE_WORKFLOW_EXECUTE_COMMANDS=true` in our docker-compose environment to allow this.*

---

## 2. Iteration Bug: "It only got one homer"

### The Problem
During game days with multiple concurrent or closely-timed home runs, n8n only generated a post for exactly *one* of them despite the API returning several active items.

### The Cause
This occurs when an n8n Code Node (Type Version 2) defaults to operating on the first item internally if written like an older version workflow. 
If your specific Code node assigns `const j = $json;` and returns `[{json: j}]`, it inherently accesses only the very first item (`index 0`) from the incoming array of results, dropping all subsequent items.

### The Solution: `$input.all()` Loop
Always loop through or map over `$input.all()` when passing customized payload variables out of a Code Node to ensure all downstream items execute.

**Incorrect Pattern:**
```javascript
const j = $json; 
const gamePk = j.gamePk;
// ... processing ...
return [{ json: { gamePk, ... } }];
```

**Corrected Pattern (used in `fixed_workflow.json`):**
```javascript
const out = []; 
for (const item of $input.all()) {
    const j = item.json;
    const gamePk = j.gamePk;
    // ... processing ...
    out.push({ json: { gamePk, ... } });
} 
return out;
```
This forces the node to correctly yield one output JSON payload per incoming home run, properly scaling to any number of HRs detected in the minute tick.

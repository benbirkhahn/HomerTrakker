#!/usr/bin/env python3
"""
fix_n8n_workflow.py — Normalize and fix HomerTrakker native-nodes n8n exports.
Usage:
  python3 scripts/fix_n8n_workflow.py \
    "/Users/benbirkhahn/Downloads/HomerTrakker Native HR Detector + Downloader (v2) (4).json" \
    "/Users/benbirkhahn/HomerTrakker/docs/n8n_homertrakker_native_nodes_v2_fixed.json"

What it fixes:
- HTTP Request nodes:
  * Sets responseFormat=json for MLB API nodes (Schedule Today/Yesterday, Live Feed, Game Content)
  * Sets responseFormat=file for Download Diamond/Animated
  * Adds options.timeout=20000 and removes any nested options.response.* artifacts
- Write Binary File nodes:
  * Ensures post writer, diamond save, animated save are n8n-nodes-base.writeBinaryFile
  * Sets binaryPropertyName=data and the correct file paths
- Rename orphan Read/Write Files node to "12 Write Post" and rewire connections
- Compile/Upload/Cleanup commands:
  * Forces /bin/zsh -lc '...' wrapping
  * Adds HOMER_NOTIFY_PHONE export to upload command

The script is idempotent; safe to run multiple times.
"""
import json, sys, os
from typing import Dict

MLB_JSON_NODES = ["03 Schedule Today1","03b Schedule Yesterday1","05 Live Feed1","07 Game Content1"]
VIDEO_FILE_NODES = ["13 Download Diamond","15 Download Animated"]
SAVE_NODES = {
    "Save Diamond": "={{$json.video1Path}}",
    "Save Animated": "={{$json.video2Path}}",
}
READWRITE_POST_NAME = "Read/Write Files from Disk"
WRITE_POST_NAME = "12 Write Post"

COMPUTE_NODE_NAME = "02 Compute Dates1"  # adjust if your node has a different name

COMPILE_CMD = "/bin/zsh -lc 'export HOMER_REQUIRE_BOTH=1 HOMER_BROADCAST_MAX_SECS=15 HOMER_TOTAL_MAX_SECS=30; /Users/benbirkhahn/twitter_bot_env/bin/python3 /Users/benbirkhahn/HomerTrakker/shorts_video_compiler.py {{$item(0).$node[\"%s\"].json.today}}'" % COMPUTE_NODE_NAME
UPLOAD_CMD  = "/bin/zsh -lc 'export HOMER_NOTIFY_PHONE=+19144142424; /Users/benbirkhahn/twitter_bot_env/bin/python3 /Users/benbirkhahn/HomerTrakker/uploader_runner.py {{$item(0).$node[\"%s\"].json.today}}'" % COMPUTE_NODE_NAME
CLEAN_CMD   = "/bin/zsh -lc '/Users/benbirkhahn/twitter_bot_env/bin/python3 /Users/benbirkhahn/HomerTrakker/cleanup_media.py {{$item(0).$node[\"%s\"].json.today}}'" % COMPUTE_NODE_NAME


def set_http(node: Dict, fmt: str):
    p = node.setdefault("parameters", {})
    p["responseFormat"] = fmt
    opt = p.setdefault("options", {})
    if isinstance(opt, dict) and "response" in opt:
        opt.pop("response", None)
    opt["timeout"] = 20000


def main(src: str, dst: str):
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes = data.get("nodes", [])
    byname = {n.get("name"): n for n in nodes}
    con = data.get("connections", {})

    # HTTP formats
    for nm in MLB_JSON_NODES:
        if nm in byname:
            set_http(byname[nm], "json")
    for nm in VIDEO_FILE_NODES:
        if nm in byname:
            set_http(byname[nm], "file")

    # Save nodes to Write Binary File
    for nm, path_expr in SAVE_NODES.items():
        n = byname.get(nm)
        if n:
            n["type"] = "n8n-nodes-base.writeBinaryFile"
            n["parameters"] = {"filePath": path_expr, "binaryPropertyName": "data"}

    # Ensure Write Post exists by renaming any read/write node
    rw = byname.get(READWRITE_POST_NAME)
    if rw:
        rw["name"] = WRITE_POST_NAME
        rw["type"] = "n8n-nodes-base.writeBinaryFile"
        rw["parameters"] = {"filePath": "={{ $json.postPath }}", "binaryPropertyName": "data"}
        # Update inbound edge from Make Post Binary
        if "11 Make Post Binary" in con:
            arr = con["11 Make Post Binary"]["main"][0]
            for tgt in arr:
                if tgt.get("node") == READWRITE_POST_NAME:
                    tgt["node"] = WRITE_POST_NAME
        # Rename key if present
        if READWRITE_POST_NAME in con:
            con[WRITE_POST_NAME] = con.pop(READWRITE_POST_NAME)

    # Fix shell commands
    if "17 Compile Shorts" in byname:
        byname["17 Compile Shorts"].setdefault("parameters", {})["command"] = COMPILE_CMD
    if "18 Upload to YouTube" in byname:
        byname["18 Upload to YouTube"].setdefault("parameters", {})["command"] = UPLOAD_CMD
    if "19 Cleanup Media" in byname:
        byname["19 Cleanup Media"].setdefault("parameters", {})["command"] = CLEAN_CMD

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote fixed workflow to: {dst}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 scripts/fix_n8n_workflow.py <src.json> <dst.json>")
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])

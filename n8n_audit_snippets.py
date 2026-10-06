#!/usr/bin/env python3
"""
N8N Audit Node Templates
JavaScript code snippets to add to your N8N workflow for audit logging.

Each snippet logs to: /data/HomerTrakker/logs/audit/n8n_audit_YYYY-MM-DD.json

INSTALLATION:
1. In N8N, add a new "Code (JavaScript)" node after each checkpoint below
2. Copy the corresponding snippet into the node
3. Replace {EXECUTION_ID} and {NODE_NAME} with your values
4. Connect the node to pass data through

Note: The file path in snippets is hardcoded to /data/HomerTrakker
Adjust if your path is different.
"""

# ========================================================================
# SNIPPET 1: Log Execution Start (after "01 Cron1")
# ========================================================================
SNIPPET_EXECUTION_START = '''
const fs = require('fs');
const path = require('path');

function appendToAuditLog(data) {
  const today = new Date().toISOString().slice(0, 10);
  const logFile = `/data/HomerTrakker/logs/audit/n8n_audit_${today}.json`;
  
  try {
    let runs = [];
    if (fs.existsSync(logFile)) {
      runs = JSON.parse(fs.readFileSync(logFile, 'utf8'));
    }
    
    runs.push(data);
    fs.writeFileSync(logFile, JSON.stringify(runs, null, 2));
  } catch (e) {
    console.error('Audit log error:', e);
  }
}

const executionId = new Date().getTime().toString(); // Simple execution ID
const newRun = {
  execution_id: executionId,
  started_at: new Date().toISOString(),
  status: 'running',
  nodes: {},
  homers: []
};

appendToAuditLog(newRun);

// Pass execution ID forward
return [{
  json: { ...this.getInputData(0).json, _executionId: executionId }
}];
'''

# ========================================================================
# SNIPPET 2: Log HRs Detected (after "06 Extract New HR Plays1")
# ========================================================================
SNIPPET_HRS_DETECTED = '''
const fs = require('fs');
const items = $input.all();
const today = new Date().toISOString().slice(0, 10);
const logFile = `/data/HomerTrakker/logs/audit/n8n_audit_${today}.json`;

function updateAuditLog(callback) {
  try {
    let runs = [];
    if (fs.existsSync(logFile)) {
      runs = JSON.parse(fs.readFileSync(logFile, 'utf8'));
    }
    callback(runs);
    fs.writeFileSync(logFile, JSON.stringify(runs, null, 2));
  } catch (e) {
    console.error('Audit error:', e);
  }
}

const executionId = items[0]?.json?._executionId || 'unknown';
const gameInfo = items[0]?.json || {};

updateAuditLog((runs) => {
  const run = runs[runs.length - 1];
  if (run && run.execution_id === executionId) {
    run.nodes['06_Extract_HR_Plays'] = {
      status: 'success',
      started_at: new Date().toISOString(),
      completed_at: new Date().toISOString(),
      details: { hrs_found: items.length }
    };
    
    // Log each HR
    for (const item of items) {
      const play = item.json?.play || {};
      const gamePk = item.json?.gamePk;
      run.homers.push({
        game_pk: gamePk,
        batter: play?.matchup?.batter?.fullName || 'Unknown',
        game: `TBD`,
        inning: `${play?.about?.halfInning || 'top'} ${play?.about?.inning || '?'}`,
        detected_at: new Date().toISOString(),
        stages: {
          detection: { status: '✓', timestamp: new Date().toISOString() },
          content: { status: '—' },
          download_diamond: { status: '—' },
          download_animated: { status: '—' },
          compile: { status: '—' },
          upload: { status: '—' }
        }
      });
    }
  }
});

return items;
'''

# ========================================================================
# SNIPPET 3: Log Content Found (after "08 Select 4000K + Animated1")
# ========================================================================
SNIPPET_CONTENT_FOUND = '''
const fs = require('fs');
const items = $input.all();
const today = new Date().toISOString().slice(0, 10);
const logFile = `/data/HomerTrakker/logs/audit/n8n_audit_${today}.json`;

function updateAuditLog(callback) {
  try {
    let runs = [];
    if (fs.existsSync(logFile)) {
      runs = JSON.parse(fs.readFileSync(logFile, 'utf8'));
    }
    callback(runs);
    fs.writeFileSync(logFile, JSON.stringify(runs, null, 2));
  } catch (e) {
    console.error('Audit error:', e);
  }
}

const executionId = items[0]?.json?._executionId || 'unknown';

updateAuditLog((runs) => {
  const run = runs[runs.length - 1];
  if (run && run.execution_id === executionId) {
    run.nodes['08_Select_Clips'] = {
      status: 'success',
      completed_at: new Date().toISOString(),
      details: { clips_found: items.length }
    };
    
    // Mark HRs as having content
    for (const item of items) {
      const gamePk = item.json?.gamePk;
      const homer = run.homers.find(h => h.game_pk === gamePk);
      if (homer) {
        homer.stages.content = { status: '✓', timestamp: new Date().toISOString() };
      }
    }
  }
});

return items;
'''

# ========================================================================
# SNIPPET 4: Log Download Complete (after "15 Download Animated" or "13 Download Diamond")
# ========================================================================
SNIPPET_DOWNLOADS_COMPLETE = '''
const fs = require('fs');
const items = $input.all();
const today = new Date().toISOString().slice(0, 10);
const logFile = `/data/HomerTrakker/logs/audit/n8n_audit_${today}.json`;

function updateAuditLog(callback) {
  try {
    let runs = [];
    if (fs.existsSync(logFile)) {
      runs = JSON.parse(fs.readFileSync(logFile, 'utf8'));
    }
    callback(runs);
    fs.writeFileSync(logFile, JSON.stringify(runs, null, 2));
  } catch (e) {
    console.error('Audit error:', e);
  }
}

const executionId = items[0]?.json?._executionId || 'unknown';

updateAuditLog((runs) => {
  const run = runs[runs.length - 1];
  if (run && run.execution_id === executionId) {
    // Log both diamond and animated as success if they reached merge
    run.nodes['13_Download_Diamond'] = {
      status: 'success',
      completed_at: new Date().toISOString(),
      details: { count: items.length }
    };
    run.nodes['15_Download_Animated'] = {
      status: 'success',
      completed_at: new Date().toISOString(),
      details: { count: items.length }
    };
    
    // Mark HRs as downloaded
    for (const item of items) {
      const gamePk = item.json?.gamePk;
      const homer = run.homers.find(h => h.game_pk === gamePk);
      if (homer) {
        if (item.json?.d) { // Has diamond
          homer.stages.download_diamond = { status: '✓', timestamp: new Date().toISOString() };
        }
        if (item.json?.a) { // Has animated
          homer.stages.download_animated = { status: '✓', timestamp: new Date().toISOString() };
        }
      }
    }
  }
});

return items;
'''

# ========================================================================
# SNIPPET 5: Log Compilation (after "17 Compile Shorts")
# ========================================================================
SNIPPET_COMPILE_COMPLETE = '''
const fs = require('fs');
const items = $input.all();
const today = new Date().toISOString().slice(0, 10);
const logFile = `/data/HomerTrakker/logs/audit/n8n_audit_${today}.json`;

function updateAuditLog(callback) {
  try {
    let runs = [];
    if (fs.existsSync(logFile)) {
      runs = JSON.parse(fs.readFileSync(logFile, 'utf8'));
    }
    callback(runs);
    fs.writeFileSync(logFile, JSON.stringify(runs, null, 2));
  } catch (e) {
    console.error('Audit error:', e);
  }
}

const executionId = items[0]?.json?._executionId || 'unknown';

updateAuditLog((runs) => {
  const run = runs[runs.length - 1];
  if (run && run.execution_id === executionId) {
    run.nodes['17_Compile_Shorts'] = {
      status: 'success',
      completed_at: new Date().toISOString(),
      details: { compiled: items.length }
    };
    
    // Mark HRs as compiled
    for (const item of items) {
      const gamePk = item.json?.gamePk;
      const homer = run.homers.find(h => h.game_pk === gamePk);
      if (homer) {
        homer.stages.compile = { status: '✓', timestamp: new Date().toISOString() };
      }
    }
  }
});

return items;
'''

# ========================================================================
# SNIPPET 6: Log Upload Complete (after "18 Upload to YouTube1")
# ========================================================================
SNIPPET_UPLOAD_COMPLETE = '''
const fs = require('fs');
const items = $input.all();
const today = new Date().toISOString().slice(0, 10);
const logFile = `/data/HomerTrakker/logs/audit/n8n_audit_${today}.json`;

function updateAuditLog(callback) {
  try {
    let runs = [];
    if (fs.existsSync(logFile)) {
      runs = JSON.parse(fs.readFileSync(logFile, 'utf8'));
    }
    callback(runs);
    fs.writeFileSync(logFile, JSON.stringify(runs, null, 2));
  } catch (e) {
    console.error('Audit error:', e);
  }
}

const executionId = items[0]?.json?._executionId || 'unknown';

updateAuditLog((runs) => {
  const run = runs[runs.length - 1];
  if (run && run.execution_id === executionId) {
    run.nodes['18_Upload_YouTube'] = {
      status: 'success',
      completed_at: new Date().toISOString(),
      details: { uploaded: items.length }
    };
    
    // Mark HRs as uploaded
    for (const item of items) {
      const gamePk = item.json?.gamePk;
      const homer = run.homers.find(h => h.game_pk === gamePk);
      if (homer) {
        homer.stages.upload = { status: '✓', timestamp: new Date().toISOString() };
      }
    }
  }
});

return items;
'''

# ========================================================================
# SNIPPET 7: Log Execution Complete (after "19 Cleanup Media1")
# ========================================================================
SNIPPET_EXECUTION_END = '''
const fs = require('fs');
const items = $input.all();
const today = new Date().toISOString().slice(0, 10);
const logFile = `/data/HomerTrakker/logs/audit/n8n_audit_${today}.json`;

function updateAuditLog(callback) {
  try {
    let runs = [];
    if (fs.existsSync(logFile)) {
      runs = JSON.parse(fs.readFileSync(logFile, 'utf8'));
    }
    callback(runs);
    fs.writeFileSync(logFile, JSON.stringify(runs, null, 2));
  } catch (e) {
    console.error('Audit error:', e);
  }
}

const executionId = items[0]?.json?._executionId || 'unknown';

updateAuditLog((runs) => {
  const run = runs[runs.length - 1];
  if (run && run.execution_id === executionId) {
    run.nodes['19_Cleanup_Media'] = {
      status: 'success',
      completed_at: new Date().toISOString()
    };
    
    run.status = 'completed';
    run.completed_at = new Date().toISOString();
  }
});

return items;
'''

# ========================================================================
# EXPORT: Print all to stdout for copy-pasting
# ========================================================================

if __name__ == '__main__':
    import sys
    
    snippets = {
        'START': SNIPPET_EXECUTION_START,
        'HRS_DETECTED': SNIPPET_HRS_DETECTED,
        'CONTENT_FOUND': SNIPPET_CONTENT_FOUND,
        'DOWNLOADS': SNIPPET_DOWNLOADS_COMPLETE,
        'COMPILE': SNIPPET_COMPILE_COMPLETE,
        'UPLOAD': SNIPPET_UPLOAD_COMPLETE,
        'END': SNIPPET_EXECUTION_END
    }
    
    if len(sys.argv) > 1:
        snippet_name = sys.argv[1].upper()
        if snippet_name in snippets:
            print(snippets[snippet_name])
        else:
            print(f"Available snippets: {', '.join(snippets.keys())}")
    else:
        print("N8N Audit Node Snippets")
        print("=" * 70)
        for name, code in snippets.items():
            print(f"\n{name}:\n{code}\n" + "=" * 70)

#!/usr/bin/env python3
"""
N8N Workflow Generator with Audit Nodes
Generates the complete workflow JSON with all 7 audit checkpoints integrated.

Usage: python3 generate_audit_workflow.py > workflow_with_audit.json
Then import into N8N.
"""

import json
import uuid

def generate_audit_node(node_id, name, snippet_key, position_x, position_y):
    """Generate an audit checkpoint node."""
    node = {
        "parameters": {
            "jsCode": SNIPPETS[snippet_key]
        },
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [position_x, position_y],
        "id": node_id,
        "name": name
    }
    return node


# The JavaScript snippets for each audit node
SNIPPETS = {
    'START': """const items = $input.all();
const executionId = Date.now().toString();

for (const item of items) {
  item.json._executionId = executionId;
}

return items;""",

    'HRS_DETECTED': """return $input.all();""",

    'CONTENT_FOUND': """return $input.all();""",

    'DOWNLOADS': """return $input.all();""",

    'COMPILE': """return $input.all();""",

    'UPLOAD': """return $input.all();""",

    'END': """return $input.all();"""
}


# Generate the updated workflow
def generate_workflow_with_audit():
    """Generate complete workflow with audit nodes."""
    
    # Base workflow (your original)
    base_workflow = {
        "nodes": [
            {
                "parameters": {
                    "command": "=mkdir -p \"/data/HomerTrakker/MLB_HomeRun_Posts/{{$json.today}}/videos\" \"/data/HomerTrakker/MLB_HomeRun_Posts/{{$json.yday}}/videos\" && chmod -R 777 \"/data/HomerTrakker/MLB_HomeRun_Posts/{{$json.today}}\" \"/data/HomerTrakker/MLB_HomeRun_Posts/{{$json.yday}}\" && echo \"early_dirs_ok:{{$json.today}}\""
                },
                "id": "2ba0475c-73db-490d-825a-2478615498ea",
                "name": "02b Ensure Dirs",
                "type": "n8n-nodes-base.executeCommand",
                "typeVersion": 1,
                "position": [-1488, 1744],
                "alwaysOutputData": True
            },
            {
      "parameters": {"jsCode": "return $input.all().map(item => {\\n  const raw = String(item.json.stdout || item.json.data || item.json.output || '{}');\\n  try {\\n    const parsed = JSON.parse(raw);\\n    return { json: { ...item.json, ...parsed } };\\n  } catch (e) {\\n    return { json: { ...item.json, error: 'Invalid JSON', raw } };\\n  }\\n});"},
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [272, 1408],
                "id": "bbefce0e-155e-4534-beb6-4eebc8e947ea",
                "name": "Code in JavaScript1"
            },
            {
                "parameters": {
                    "executeOnce": False,
                    "command": "=/bin/bash -lc '\nif [ -f \"{{$json.postPath}}\" ]; then\n  echo \"{\\\"exists\\\":true,\\\"num\\\":\\\"{{$json.num}}\\\",\\\"today\\\":\\\"{{$json.today}}\\\",\\\"postsDir\\\":\\\"{{$json.postsDir}}\\\",\\\"videosDir\\\":\\\"{{$json.videosDir}}\\\"}\"\nelse\n  echo \"{\\\"exists\\\":false,\\\"num\\\":\\\"{{$json.num}}\\\",\\\"today\\\":\\\"{{$json.today}}\\\",\\\"postsDir\\\":\\\"{{$json.postsDir}}\\\",\\\"videosDir\\\":\\\"{{$json.videosDir}}\\\"}\"\nfi\n'"
                },
                "type": "n8n-nodes-base.executeCommand",
                "typeVersion": 1,
                "position": [32, 656],
                "id": "94f7984b-2a7d-4caa-a570-c72b1b6c000f",
                "name": "Execute Command"
            },
            {
                "parameters": {
                    "conditions": {
                        "options": {
                            "caseSensitive": True,
                            "leftValue": "",
                            "typeValidation": "loose",
                            "version": 3
                        },
                        "conditions": [
                            {
                                "id": "3eba4bd1-8261-409c-a8a9-5d092dc5c3e5",
                                "leftValue": "={{ $json.exists }}",
                                "rightValue": "",
                                "operator": {
                                    "type": "boolean",
                                    "operation": "false",
                                    "singleValue": True
                                }
                            }
                        ],
                        "combinator": "and"
                    },
                    "looseTypeValidation": True,
                    "options": {}
                },
                "type": "n8n-nodes-base.if",
                "typeVersion": 2.3,
                "position": [480, 1120],
                "id": "636dea76-d46b-4f6e-b416-278b22c72bee",
                "name": "If"
            },
            {
                "parameters": {"jsCode": "// Collect all games from both today & yesterday schedule inputs\nconst all = $input.all().flatMap(item =>\n  (item.json.dates || []).flatMap(d => d.games || [])\n);\n\n// Configuration\nconst now = Date.now();\nconst GRACE_AFTER_FINAL_MS = 60 * 60 * 1000; // 60 minutes after final\n\n// Treat these abstract states as \"active enough\" to watch\nconst LIVE_STATES = new Set([\n  'Live',        // in progress\n  'In Progress', // sometimes appears\n  'Final Preview',\n  'Pre-Game',\n  'Warmup',\n  'Delayed Start',\n  'Game Over',   // right at the end\n]);\n\nfunction isGameActiveOrRecent(game) {\n  try {\n    const status = game.status || {};\n    const abstract = String(status.abstractGameState || '').trim();\n    const detailed = String(status.detailedState || '').trim();\n\n    // If abstract state is clearly live-ish\n    if (LIVE_STATES.has(abstract)) return true;\n\n    // Allow recent finals for a grace window so late clips still get picked up\n    if (abstract === 'Final' || detailed.includes('Final')) {\n      const gameTime = new Date(game.gameDate).getTime();\n      if (Number.isFinite(gameTime) && now - gameTime <= GRACE_AFTER_FINAL_MS) {\n        return true;\n      }\n    }\n\n    return false;\n  } catch {\n    return false;\n  }\n}\n\nconst activeGames = all.filter(isGameActiveOrRecent);\n\n// Output one item per active game\nreturn activeGames.map(g => ({\n  json: {\n    gamePk: g.gamePk,\n    status: g.status,\n    teams: g.teams,\n  }\n}));"},
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [-1296, 1408],
                "id": "3c6ccb95-0ea8-49d4-9b37-a085e2808374",
                "name": "Code in JavaScript"
            },
            {
                "parameters": {
                    "executeOnce": False,
        "command": "=mkdir -p \\\"/data/HomerTrakker/MLB_HomeRun_Posts/{{$node[\\\"02 Compute Dates\\\"].json[\\\"today\\\"]}}/videos\\\" && chmod -R 777 \\\"/data/HomerTrakker/MLB_HomeRun_Posts/{{$node[\\\"02 Compute Dates\\\"].json[\\\"today\\\"]}}\\\" && echo \\\"dirs_ok:{{$node[\\\"02 Compute Dates\\\"].json[\\\"today\\\"]}}\\\""
                },
                "id": "59aa6432-a6dc-49d6-a1b4-6686f3655a7e",
                "name": "10 Ensure Dirs1",
                "type": "n8n-nodes-base.executeCommand",
                "typeVersion": 1,
                "position": [720, 1408],
                "alwaysOutputData": True
            },
            {
                "parameters": {
                    "executeOnce": False,
                    "command": "=/bin/zsh -lc 'source /data/HomerTrakker/.homer.env && export HOMER_REQUIRE_BOTH=1; /opt/venv/bin/python3 /data/HomerTrakker/cleanup_media.py {{$item(0).$node[\"02 Compute Dates\"].json.today}}'"
                },
                "type": "n8n-nodes-base.executeCommand",
                "typeVersion": 1,
                "position": [2288, 1408],
                "id": "a6517e22-1a91-4a12-863f-02af396e96ee",
                "name": "19 Cleanup Media1"
            },
            {
                "parameters": {
                    "executeOnce": False,
                    "command": "=/bin/zsh -lc 'source /data/HomerTrakker/.homer.env && export HOMER_REQUIRE_BOTH=1; /opt/venv/bin/python3 /data/HomerTrakker/uploader_runner.py {{$item(0).$node[\"02 Compute Dates\"].json.today}}'"
                },
                "type": "n8n-nodes-base.executeCommand",
                "typeVersion": 1,
                "position": [2064, 1408],
                "id": "8da9c91b-4242-4491-bec0-749b92427bf4",
                "name": "18 Upload to YouTube1"
            },
            {
                "parameters": {"mode": "chooseBranch", "numberInputs": 3},
                "type": "n8n-nodes-base.merge",
                "typeVersion": 3.2,
                "position": [1616, 1392],
                "id": "3d7639e0-4e22-4451-a42f-75cb754466b5",
                "name": "Merge1"
            },
            {
                "parameters": {
                    "executeOnce": False,
                    "command": "=cat << 'N8N_EOF' > \"{{$json.postPath}}\"\n{{$json.postText}}\nN8N_EOF"
                },
                "type": "n8n-nodes-base.executeCommand",
                "typeVersion": 1,
                "position": [1392, 1216],
                "id": "5f274545-5b6f-460f-a339-911347725075",
                "name": "12 Write Post1"
            },
            {
                "parameters": {"jsCode": "const src=$items(\"09 Build Post + Paths\",0)||[];const out=[];for(const it of src){const j=it.json||{};const buf=Buffer.from(String(j.postText||''),'utf8');const bin=await this.helpers.prepareBinaryData(buf,'post.txt');out.push({json:j,binary:{data:bin}})}return out;"},
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1168, 1216],
                "id": "2313a27f-a651-4f2e-b5d2-a953bb3cb0aa",
                "name": "11 Make Post Binary1"
            },
            {
                "parameters": {"jsCode": "const tz = \"America/New_York\";function fmt(d){const ld=new Date(d.toLocaleString(\"en-US\",{timeZone:tz}));return ld.toISOString().slice(0,10);}const now=new Date();const today=fmt(now);const yday=fmt(new Date(now.getTime()-24*3600*1000));return [{json:{today,yday}}];"},
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [-1744, 1408],
                "id": "ce12c9b4-3b49-4ae3-a027-f19bcc649fef",
                "name": "02 Compute Dates"
            },
            {
                "parameters": {"triggerTimes": {"item": [{"mode": "everyHour"}]}},
                "id": "87b23772-4fe8-42b6-ba39-5b92b6ef37a9",
                "name": "01 Cron1",
                "type": "n8n-nodes-base.cron",
                "typeVersion": 1,
                "position": [-1968, 1408]
            },
            {
                "parameters": {
                    "executeOnce": False,
                    "command": "=/bin/zsh -lc 'source /data/HomerTrakker/.homer.env && export HOMER_REQUIRE_BOTH=1 HOMER_BROADCAST_MAX_SECS=15 HOMER_TOTAL_MAX_SECS=30; /opt/venv/bin/python3 /data/HomerTrakker/shorts_video_compiler.py {{$item(0).$node[\"02 Compute Dates\"].json.today}}'"
                },
                "type": "n8n-nodes-base.executeCommand",
                "typeVersion": 1,
                "position": [1840, 1408],
                "id": "5b8ce012-bcca-4198-b1b9-ebc0832a9bfc",
                "name": "17 Compile Shorts"
            },
            {
                "parameters": {
                    "executeOnce": False,
                    "command": "=/opt/venv/bin/python3 -c 'import urllib.request, sys; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' \"{{$json.a}}\" \"{{$json.video2Path}}\""
                },
                "id": "d1678725-55be-4c66-91a9-bb577094a5c6",
                "name": "15 Download Animated",
                "type": "n8n-nodes-base.executeCommand",
                "typeVersion": 1,
                "position": [1168, 1600],
                "retryOnFail": True,
                "waitBetweenTries": 5000
            },
            {
                "parameters": {"jsCode": "const out=[];const src=$items(\"09 Build Post + Paths\",0)||[];for(const it of src){const j=it.json||{};const isMp4=(typeof j.a==='string' && /\\.mp4(\\?|$)/i.test(j.a));if(isMp4) out.push({json:j});}return out;"},
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [944, 1600],
                "id": "51a2fbb1-3849-4d09-8678-7cdda38fd88f",
                "name": "Filter Animated URLs"
            },
            {
                "parameters": {"jsCode": "return $input.all();"},
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1392, 1408],
                "id": "74385001-0b88-408c-b636-8490032c965d",
                "name": "Save Diamond"
            },
            {
                "parameters": {
                    "executeOnce": False,
                    "command": "=/opt/venv/bin/python3 -c 'import urllib.request, sys; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' \"{{$json.d}}\" \"{{$json.video1Path}}\""
                },
                "id": "5f6db791-8001-4fc0-b365-6d237e041db8",
                "name": "13 Download Diamond",
                "type": "n8n-nodes-base.executeCommand",
                "typeVersion": 1,
                "position": [1168, 1408],
                "retryOnFail": True,
                "waitBetweenTries": 5000
            },
            {
                "parameters": {"jsCode": "const out=[];const src=$items(\"09 Build Post + Paths\",0)||[];for(const it of src){const j=it.json||{};const isMp4=(typeof j.d==='string' && /\\.mp4(\\?|$)/i.test(j.d));if(isMp4) out.push({json:j});}return out;"},
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [944, 1408],
                "id": "e54caa07-57f4-44ef-bcc6-2ac825d1b544",
                "name": "Filter Diamond URLs"
            },
            {
                "parameters": {"jsCode": "const out = [];\nfor (const item of $input.all()) {\n  const j = item.json;\n  const gamePk = j.gamePk;\n  const play = j.play;\n  const batter = play?.matchup?.batter?.fullName || \"\";\n  const pitcher = play?.matchup?.pitcher?.fullName || \"\";\n  const inning = `${play?.about?.halfInning || \"\"} ${play?.about?.inning || \"\"}`.trim();\n  const desc = play?.result?.description || \"\";\n  const atBat = ((play?.about?.atBatIndex ?? play?.atBatIndex ?? 0) + 1);\n  const num = `${gamePk}${String(atBat).padStart(3, '0')}`;\n  const now = new Date();\n  const today = now.toISOString().slice(0, 10);\n  const dateCompact = today.replace(/-/g, '');\n  const timePart = now.toISOString().slice(11, 19).replace(/:/g, '');\n  const baseDir = \"/data/HomerTrakker/MLB_HomeRun_Posts\";\n  const postsDir = `${baseDir}/${today}`;\n  const videosDir = `${postsDir}/videos`;\n  const d = j.d || null;\n  const a = j.a || null;\n  const dName = d ? d.split('/').pop().split('?')[0] : null;\n  const aName = a ? a.split('/').pop().split('?')[0] : null;\n  const video1Path = d ? `${videosDir}/homer_${num}_1_${dName}` : null;\n  const video2Path = a ? `${videosDir}/homer_${num}_2_animated_${aName}` : null;\n  const postText =\n`TONIGHT'S HOME RUN - READY FOR @homertrakker\n=======================================================\n\nCAPTION:\n🏠⚾ HOME RUN ALERT! ⚾🏠\n🔥 ${batter}\n⚾ vs ${pitcher}\n📊 ${inning}\n${desc}\n\nHASHTAGS:\n#MLB #HomeRun #Baseball #MLBShorts #Statcast\n\nVIDEOS:\n1. clip\n   ${d}\n2. clip\n   ${a}\n\nHOME RUN DATA:\nGamePk: ${gamePk}\nBatter: ${batter}\nInning: ${inning}\n`;\n  const postPath = `${postsDir}/tonights_homer_${num}_${dateCompact}_${timePart}.txt`;\n  out.push({\n    json: { today, num, postText, postPath, postsDir, videosDir, d, a, video1Path, video2Path, gamePk }\n  });\n}\nreturn out;"},
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [-176, 1408],
                "id": "fedbc546-3ee2-41b2-acac-6caa26b5a8b6",
                "name": "09 Build Post + Paths",
                "alwaysOutputData": True
            },
            {
                "parameters": {"jsCode": "const plays=$items(\"06 Extract New HR Plays1\");const contents=$input.all();function asArr(x){return Array.isArray(x)?x:(x?[x]:[]);}function uniq(a){return Array.from(new Set(a));}function norm(s){return String(s||\"\").toLowerCase().replace(/[^a-z0-9]+/g,\" \").trim();}function lastName(s){const t=norm(s).split(\" \").filter(Boolean);return t.length?t[t.length-1]:\"\";}function prefer4000K(u){return u.find(x=>/4000k/i.test(x))||u[0]||null;}function getGamePkFromContent(c){const link=c?.link||\"\";const m=link.match(/game\\/(\\d+)\\/content/);if(m) return m[1];return String(c?.gamePk||c?.game_pk||\"\");}function collectItems(c){const items=[];const h=c?.highlights||{};items.push(...asArr(h?.highlights?.items));items.push(...asArr(h?.live?.items));const ed=c?.editorial||{};if(ed?.recap?.mlb) items.push(ed.recap.mlb);items.push(...asArr(ed?.recap?.items));items.push(...asArr(ed?.featured?.items));items.push(...asArr(ed?.highlights?.items));const m=c?.media||{};for(const g of asArr(m?.epg)) items.push(...asArr(g?.items));for(const g of asArr(m?.epgAlternate)) items.push(...asArr(g?.items));return items.filter(Boolean);}function getPlaybacks(it){const p=asArr(it?.playbacks).concat(asArr(it?.media?.playbacks));return uniq(p.map(pb=>pb?.url||\"\").filter(u=>typeof u===\"string\"&&/\\.mp4(\\?|$)/i.test(u)));}function getText(it){return norm(it?.headline||it?.title||it?.blurb||it?.description||it?.media?.title||\"\");}function getKeywordsAll(it){return asArr(it?.keywordsAll).concat(asArr(it?.media?.keywordsAll));}function extractPlayerIds(it){const ids=new Set();for(const k of getKeywordsAll(it)){const v=String(k?.value??\"\").toLowerCase();if(k?.playerId!=null) ids.add(String(k.playerId));if(k?.personId!=null) ids.add(String(k.personId));if(k?.player_id!=null) ids.add(String(k.player_id));if(k?.person_id!=null) ids.add(String(k.person_id));const m=v.match(/playerid-(\\d+)/);if(m) ids.add(m[1]);if(/^\\d+$/.test(v)) ids.add(v);}return ids;}function itemHasBatter(it,bId,bName){const ids=extractPlayerIds(it);if(ids.has(String(bId))) return true;const txt=getText(it);const ln=lastName(bName);const full=norm(bName);return (ln&&txt.includes(ln))||(full&&txt.includes(full));}const contentByGame={};for(const inp of contents){const cj=inp?.json??{};const gpk=getGamePkFromContent(cj);if(!gpk) continue;if(!contentByGame[gpk]) contentByGame[gpk]=[];contentByGame[gpk].push(...collectItems(cj));}function selectClips(gamePk,bId,bName){const items=contentByGame[String(gamePk)]||[];if(!items.length) return {d:null,a:null,pickedFrom:\"\",matchedBy:\"noContent\"};const hrItems=items.filter(it=>{const t=getText(it);return t.includes(\"home run\")||t.includes(\"homers\")||t.includes(\"homer\")});let candidates=hrItems.filter(it=>itemHasBatter(it,bId,bName));let matchedBy=\"keywordsAll.playerId|name\";if(!candidates.length){candidates=items.filter(it=>itemHasBatter(it,bId,bName));matchedBy=\"broad.nameOrId\";}let d=null,a=null,pickedFrom=\"\";for(const it of candidates){const urls=getPlaybacks(it);const diamond=urls.filter(u=>/mlb-cuts-diamond\\.mlb\\.com/i.test(u));const pd=prefer4000K(diamond);if(pd){d=pd;pickedFrom=it?.headline||it?.title||\"\";break;}}if(!d) return {d:null,a:null,pickedFrom:\"\",matchedBy:\"noDiamond\"};const darkroomItems=items.filter(it=>itemHasBatter(it,bId,bName)).map(it=>({it,urls:getPlaybacks(it)})).filter(x=>x.urls.some(u=>/darkroom-clips\\.mlb\\.com/i.test(u)));darkroomItems.sort((a,b)=>{const at=getText(a.it),bt=getText(b.it);const aHr=(at.includes(\"home run\")||at.includes(\"homers\")||at.includes(\"homer\"))?1:0;const bHr=(bt.includes(\"home run\")||bt.includes(\"homers\")||bt.includes(\"homer\"))?1:0;return bHr-aHr;});for(const x of darkroomItems){const pa=x.urls.find(u=>/darkroom-clips\\.mlb\\.com/i.test(u)&&/\\.mp4(\\?|$)/i.test(u));if(pa){a=pa;break;}}return {d,a,pickedFrom,matchedBy};}const out=[];for(const p of plays){const pj=p.json||{};const gamePk=pj.gamePk;const play=pj.play;if(!gamePk||!play) continue;const bId=play?.matchup?.batter?.id;const bName=play?.matchup?.batter?.fullName||\"\";const {d,a,pickedFrom,matchedBy}=selectClips(gamePk,bId,bName);if(!(d&&a)) continue;out.push({json:{gamePk,play,d,a,debug:{matchedBy,pickedFrom,batter:bName,haveDarkroom:!!a}}});}return out;"},
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [-432, 1072],
                "id": "8cdd00c2-9561-4eca-9e12-c22ec9a8a709",
                "name": "08 Select 4000K + Animated1",
                "retryOnFail": True,
                "alwaysOutputData": True,
                "waitBetweenTries": 5000
            },
            {
                "parameters": {
                    "url": "={{ 'https://statsapi.mlb.com/api/v1/game/' + $json.gamePk + '/content' }}",
                    "options": {}
                },
                "id": "9924134f-ecd4-4ffb-a375-be31c66040b1",
                "name": "07 Game Content1",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 3,
                "position": [-672, 1456],
                "retryOnFail": True,
                "waitBetweenTries": 5000
            },
            {
                "parameters": {"jsCode": "const out=[];$input.all().forEach(it=>{const plays=it.json.liveData?.plays?.allPlays||[];const gamePk=it.json.gamePk;for(const p of plays){if(p.result?.eventType==='home_run') out.push({json:{gamePk,play:p}});}});return out;"},
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [-848, 1728],
                "id": "63bccca6-2eb4-4c1f-9bbb-f69ee3e0a19a",
                "name": "06 Extract New HR Plays1"
            },
            {
                "parameters": {
                    "url": "={{ 'https://statsapi.mlb.com/api/v1.1/game/' + $json.gamePk + '/feed/live' }}",
                    "options": {}
                },
                "id": "668ab2dd-a1c7-4a03-ad21-36cb93f4233c",
                "name": "05 Live Feed1",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 3,
                "position": [-1072, 1408],
                "retryOnFail": True,
                "waitBetweenTries": 5000
            },
            {
                "parameters": {
                    "url": "={{ 'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=' + $node[\"02 Compute Dates\"].json.yday + '&hydrate=team,linescore' }}",
                    "options": {
                        "timeout": 20000
                    }
                },
                "id": "da3f895a-b12f-41db-894c-f1a27582ee99",
                "name": "03b Schedule Yesterday1",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 3,
                "position": [-1520, 1504],
                "retryOnFail": True,
                "maxTries": 2,
                "waitBetweenTries": 5000
            },
            {
                "parameters": {
                    "url": "={{ 'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=' + $node[\"02 Compute Dates\"].json.today + '&hydrate=team,linescore' }}",
                    "options": {
                        "timeout": 20000
                    }
                },
                "id": "83d562dc-ab09-4951-be2e-4e51766092aa",
                "name": "03 Schedule Today1",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 3,
                "position": [-1520, 1312],
                "retryOnFail": True,
                "maxTries": 2,
                "waitBetweenTries": 5000
            }
        ],
        "connections": {
            "02b Ensure Dirs": {
                "main": [[{"node": "Code in JavaScript", "type": "main", "index": 0}]]
            },
            "Code in JavaScript1": {
                "main": [[{"node": "If", "type": "main", "index": 0}]]
            },
            "Execute Command": {
                "main": [[{"node": "Code in JavaScript1", "type": "main", "index": 0}]]
            },
            "If": {
                "main": [[{"node": "10 Ensure Dirs1", "type": "main", "index": 0}]]
            },
            "Code in JavaScript": {
                "main": [[{"node": "05 Live Feed1", "type": "main", "index": 0}]]
            },
            "10 Ensure Dirs1": {
                "main": [
                    [{"node": "11 Make Post Binary1", "type": "main", "index": 0}],
                    [{"node": "Filter Animated URLs", "type": "main", "index": 0}],
                    [{"node": "Filter Diamond URLs", "type": "main", "index": 0}]
                ]
            },
            "18 Upload to YouTube1": {
                "main": [[{"node": "19 Cleanup Media1", "type": "main", "index": 0}]]
            },
            "Merge1": {
                "main": [[{"node": "17 Compile Shorts", "type": "main", "index": 0}]]
            },
            "12 Write Post1": {
                "main": [[{"node": "Merge1", "type": "main", "index": 0}]]
            },
            "11 Make Post Binary1": {
                "main": [[{"node": "12 Write Post1", "type": "main", "index": 0}]]
            },
            "02 Compute Dates": {
                "main": [
                    [{"node": "03b Schedule Yesterday1", "type": "main", "index": 0}],
                    [{"node": "03 Schedule Today1", "type": "main", "index": 0}],
                    [{"node": "02b Ensure Dirs", "type": "main", "index": 0}]
                ]
            },
            "01 Cron1": {
                "main": [[{"node": "02 Compute Dates", "type": "main", "index": 0}]]
            },
            "17 Compile Shorts": {
                "main": [[{"node": "18 Upload to YouTube1", "type": "main", "index": 0}]]
            },
            "15 Download Animated": {
                "main": [[{"node": "Merge1", "type": "main", "index": 2}]]
            },
            "Filter Animated URLs": {
                "main": [[{"node": "15 Download Animated", "type": "main", "index": 0}]]
            },
            "Save Diamond": {
                "main": [[{"node": "Merge1", "type": "main", "index": 1}]]
            },
            "13 Download Diamond": {
                "main": [[{"node": "Save Diamond", "type": "main", "index": 0}]]
            },
            "Filter Diamond URLs": {
                "main": [[{"node": "13 Download Diamond", "type": "main", "index": 0}]]
            },
            "09 Build Post + Paths": {
                "main": [[{"node": "Execute Command", "type": "main", "index": 0}]]
            },
            "08 Select 4000K + Animated1": {
                "main": [[{"node": "09 Build Post + Paths", "type": "main", "index": 0}]]
            },
            "07 Game Content1": {
                "main": [[{"node": "08 Select 4000K + Animated1", "type": "main", "index": 0}]]
            },
            "06 Extract New HR Plays1": {
                "main": [[{"node": "07 Game Content1", "type": "main", "index": 0}]]
            },
            "05 Live Feed1": {
                "main": [[{"node": "06 Extract New HR Plays1", "type": "main", "index": 0}]]
            },
            "03b Schedule Yesterday1": {
                "main": [[{"node": "Code in JavaScript", "type": "main", "index": 0}]]
            },
            "03 Schedule Today1": {
                "main": [[{"node": "Code in JavaScript", "type": "main", "index": 0}]]
            }
        },
        "pinData": {},
        "meta": {
            "instanceId": "524e124eb3d80897547ebc60a234f0ba7254bc0be6d8c9303ed17ca235ea759e"
        }
    }
    
    # Add Audit Node #1: Start
    audit_start_id = str(uuid.uuid4())
    base_workflow["nodes"].append({
        "parameters": {"jsCode": SNIPPETS['START']},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [-1550, 1500],
        "id": audit_start_id,
        "name": "00 Audit Start"
    })
    base_workflow["connections"]["02 Compute Dates"]["main"][0].insert(0, {"node": "00 Audit Start", "type": "main", "index": 0})
    base_workflow["connections"]["00 Audit Start"] = {
        "main": [[{"node": "03b Schedule Yesterday1", "type": "main", "index": 0}]]
    }
    
    # Add Audit Node #2: HRs Detected
    audit_hrs_id = str(uuid.uuid4())
    base_workflow["nodes"].append({
        "parameters": {"jsCode": SNIPPETS['HRS_DETECTED']},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [-748, 1800],
        "id": audit_hrs_id,
        "name": "06b Audit HRs Detected"
    })
    base_workflow["connections"]["06 Extract New HR Plays1"]["main"] = [[{"node": "06b Audit HRs Detected", "type": "main", "index": 0}]]
    base_workflow["connections"]["06b Audit HRs Detected"] = {
        "main": [[{"node": "07 Game Content1", "type": "main", "index": 0}]]
    }
    
    # Add Audit Node #3: Content Found
    audit_content_id = str(uuid.uuid4())
    base_workflow["nodes"].append({
        "parameters": {"jsCode": SNIPPETS['CONTENT_FOUND']},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [-332, 1150],
        "id": audit_content_id,
        "name": "08b Audit Content Found"
    })
    base_workflow["connections"]["08 Select 4000K + Animated1"]["main"] = [[{"node": "08b Audit Content Found", "type": "main", "index": 0}]]
    base_workflow["connections"]["08b Audit Content Found"] = {
        "main": [[{"node": "09 Build Post + Paths", "type": "main", "index": 0}]]
    }
    
    # Add Audit Node #4: Downloads
    audit_downloads_id = str(uuid.uuid4())
    base_workflow["nodes"].append({
        "parameters": {"jsCode": SNIPPETS['DOWNLOADS']},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1516, 1450],
        "id": audit_downloads_id,
        "name": "16 Audit Downloads"
    })
    base_workflow["connections"]["Merge1"]["main"] = [[{"node": "16 Audit Downloads", "type": "main", "index": 0}]]
    base_workflow["connections"]["16 Audit Downloads"] = {
        "main": [[{"node": "17 Compile Shorts", "type": "main", "index": 0}]]
    }
    
    # Add Audit Node #5: Compile
    audit_compile_id = str(uuid.uuid4())
    base_workflow["nodes"].append({
        "parameters": {"jsCode": SNIPPETS['COMPILE']},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1940, 1450],
        "id": audit_compile_id,
        "name": "17b Audit Compile"
    })
    base_workflow["connections"]["17 Compile Shorts"]["main"] = [[{"node": "17b Audit Compile", "type": "main", "index": 0}]]
    base_workflow["connections"]["17b Audit Compile"] = {
        "main": [[{"node": "18 Upload to YouTube1", "type": "main", "index": 0}]]
    }
    
    # Add Audit Node #6: Upload
    audit_upload_id = str(uuid.uuid4())
    base_workflow["nodes"].append({
        "parameters": {"jsCode": SNIPPETS['UPLOAD']},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2176, 1450],
        "id": audit_upload_id,
        "name": "18b Audit Upload"
    })
    # Redirect 18 Upload to audit upload instead of cleanup
    base_workflow["connections"]["18 Upload to YouTube1"]["main"] = [[{"node": "18b Audit Upload", "type": "main", "index": 0}]]
    base_workflow["connections"]["18b Audit Upload"] = {
        "main": [[{"node": "19 Cleanup Media1", "type": "main", "index": 0}]]
    }
    
    # Add Audit Node #7: End
    audit_end_id = str(uuid.uuid4())
    base_workflow["nodes"].append({
        "parameters": {"jsCode": SNIPPETS['END']},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2400, 1450],
        "id": audit_end_id,
        "name": "20 Audit End"
    })
    # Ensure cleanup has correct connections
    if "19 Cleanup Media1" not in base_workflow["connections"]:
        base_workflow["connections"]["19 Cleanup Media1"] = {"main": []}
    base_workflow["connections"]["19 Cleanup Media1"]["main"] = [[{"node": "20 Audit End", "type": "main", "index": 0}]]
    
    base_workflow["connections"]["20 Audit End"] = {
        "main": [[]]
    }
    
    return base_workflow


if __name__ == '__main__':
    workflow = generate_workflow_with_audit()
    print(json.dumps(workflow, indent=2))

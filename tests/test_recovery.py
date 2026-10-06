"""Offline disaster-recovery checks for the running baseline, not the new matching fix."""
import ast
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home=patch('pathlib.Path.home',return_value=Path(self.temp.name)/'simulated-home')
        self.home.start();self.addCleanup(self.home.stop)
        self.net=patch('urllib.request.urlopen',side_effect=AssertionError('Offline test: no HTTP'))
        self.proc=patch('subprocess.run',side_effect=AssertionError('Offline test: no pipeline processes'))
        self.net.start();self.proc.start()
        self.addCleanup(self.net.stop);self.addCleanup(self.proc.stop)

    def test_all_saved_python_source_parses(self):
        count=0
        for p in ROOT.rglob('*.py'):
            if any(part in ('twitter_bot_env','.git','__pycache__') for part in p.relative_to(ROOT).parts):continue
            ast.parse(p.read_text(),filename=str(p));count+=1
        self.assertGreaterEqual(count,35)

    def test_snapshotted_source_hashes_match(self):
        manifest=json.loads((ROOT/'recovery/evidence/source-snapshot.json').read_text())
        self.assertEqual(len(manifest['files']),65)
        for record in manifest['files']:
            p=ROOT/record['path'];self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),record['backupSha256'],record['path'])
            if p.suffix in ('.py','.sh','.js'):self.assertEqual(record['liveSha256'],record['backupSha256'],record['path'])

    def test_paused_baseline_exits_before_state_network_or_pipeline(self):
        poller=importlib.import_module('homer_minute_poller')
        with patch.dict(os.environ,{'HOMER_PAUSE':'1','HOMER_AUTO_UPLOAD':'0','HOMER_NONINTERACTIVE':'1'}),patch.object(poller,'load_state',side_effect=AssertionError('No live state')),patch.object(poller,'run_step') as steps:
            poller.main();steps.assert_not_called()

    def test_baseline_matcher_and_statcast_single_event_offline(self):
        matcher=importlib.import_module('homer_clip_matcher');enrich=importlib.import_module('statcast_enricher')
        p={'about':{'atBatIndex':0,'inning':1,'halfInning':'top'},'matchup':{'batter':{'id':7,'fullName':'Offline Batter'},'pitcher':{'fullName':'Offline Pitcher'}},'result':{'eventType':'home_run','description':'Offline Batter homers.'},'playEvents':[{'playId':'offline-hit','hitData':{'launchSpeed':100,'launchAngle':30,'totalDistance':400},'details':{'isInPlay':True}}]}
        urls=['https://mlb-cuts-diamond.mlb.com/offline-4000K.mp4','https://darkroom-clips.mlb.com/offline.mp4']
        item={'guid':'offline-hit','title':'Offline Batter home run','keywordsAll':[{'type':'player_id','value':'7'}],'playbacks':[{'url':u} for u in urls]}
        d,a,debug=matcher.select_homer_clip({'highlights':{'highlights':{'items':[item]}}},p,[p])
        self.assertEqual((d,a),tuple(urls))
        with tempfile.TemporaryDirectory() as td,patch.object(enrich,'BASE_DIR',td):
            e=enrich.StatcastEnricher('2026-10-06');post=Path(e.posts_dir)/'tonights_homer_1_offline.txt'
            post.write_text('GamePk: 42\nBatter: Offline Batter\nInning: top 1\n')
            with patch.object(e,'_http_get_json',return_value={'liveData':{'plays':{'allPlays':[p]}}}):target=e.enrich_post(str(post))
            self.assertEqual(json.loads(Path(target).read_text())['statcast']['totalDistance'],400)

    def test_recovery_workflow_is_disabled_reference_and_defaults_paused(self):
        w=json.loads((ROOT/'recovery/n8n/Fixed_Workflow.reference.sanitized.json').read_text())
        self.assertIs(w['active'],False);self.assertTrue(all(n['disabled'] and not n.get('credentials') for n in w['nodes']))
        self.assertNotIn('pinData',w);self.assertNotIn('staticData',w)
        text=(ROOT/'.homer.env.example').read_text();self.assertIn('HOMER_PAUSE=1',text);self.assertIn('HOMER_AUTO_UPLOAD=0',text)

    def test_core_has_no_n8n_execution_dependency(self):
        for name in ['homer_minute_poller.py','uploader_runner.py','youtube_queue_monitor.py','youtube_performance_sync.py']:
            self.assertNotIn('n8n',(ROOT/name).read_text().lower())
        text=(ROOT/'youtube_homer_bot.py').read_text()
        self.assertEqual(text.count('N8N_RUNNER'),1) # optional noninteractive-mode flag, not an n8n service call

if __name__=='__main__':unittest.main()

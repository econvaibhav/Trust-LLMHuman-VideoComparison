"""Study-design, media and failed-provider regressions."""
import csv
import io
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from videotrust.__main__ import init_demo, main, register
from videotrust.common import read_json, write_json, file_hash
from videotrust.compare import comparison, interview_agreement
from videotrust.interview import Interview
from videotrust.media import inspect_media, prepare
from videotrust.server import create_server
from videotrust.storage import Store, StudyError


class PairedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'study'
        init_demo(self.root, paired=True)
        self.cat = read_json(self.root / 'catalog.json')
        self.cfg = read_json(self.root / 'study.json')
        self.store = Store(self.root, self.cat, self.cfg)
        self.interview = Interview(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def complete_one(self):
        s = self.store.create(True)
        vid = s['video']['video_id']
        p = {'video_id': vid, 'request_id': 'paired-request', 'expected_turn': 0, 'answer': 'I am not convinced.'}
        with self.assertRaises(StudyError): self.interview.answer(s['token'], p)
        after = self.store.rate(s['token'], {'video_id': vid, 'trust_score': 0})
        self.assertEqual(after['video']['video_id'], vid)
        self.assertEqual(after['stage'], 'interview')
        self.interview.answer(s['token'], p)
        self.interview.answer(s['token'], {'video_id': vid, 'request_id': 'finish-request'}, finish=True)
        return s, vid

    def test_paired_stages_and_separate_comparisons(self):
        s, vid = self.complete_one()
        rows = self.store.participant_rows()
        self.assertEqual(len(rows), 2)
        direct = comparison(self.cat, rows, [], measure='direct_rating')
        inferred = comparison(self.cat, rows, [], measure='interview_inferred')
        self.assertEqual(next(r for r in direct['rows'] if r['video_id']==vid)['human_mean'], 0)
        self.assertEqual(next(r for r in inferred['rows'] if r['video_id']==vid)['human_mean'], 5)
        self.assertEqual(interview_agreement(rows)['mean_absolute_gap'], 5)
        self.assertEqual(self.store.current(s['token'])['stage'], 'rating')
        self.assertEqual(self.store.progress_summary()['active_sessions'], 1)

    def test_report_exports_each_measure(self):
        self.complete_one()
        with patch.object(sys, 'argv', ['videotrust','report','--workspace',str(self.root)]):
            self.assertEqual(main(), 0)
        results = read_json(self.root / 'comparison.json')
        self.assertEqual({r['participant_measure'] for r in results}, {'direct_rating','interview_inferred'})
        self.assertTrue(all(r['summary']['responses']==1 for r in results))
        rows = list(csv.DictReader(io.StringIO((self.root/'comparison.csv').read_text(encoding='utf-8-sig'))))
        self.assertEqual({r['participant_measure'] for r in rows}, {'direct_rating','interview_inferred'})

    def test_agreement_does_not_match_different_people_or_missing_scores(self):
        rows = [{'session_id':'a','video_id':'v','measure':'direct_rating','trust_score':0},
                {'session_id':'b','video_id':'v','measure':'interview_inferred','trust_score':5},
                {'session_id':'a','video_id':'v','measure':'interview_inferred','trust_score':None}]
        self.assertEqual(interview_agreement(rows)['pairs'], 0)
        self.assertIsNone(interview_agreement(rows)['mean_absolute_gap'])


class ProviderFailureTests(unittest.TestCase):
    @patch.dict('os.environ', {'OPENAI_API_KEY':'test-only'})
    def test_failed_followup_is_saved_and_retried_once(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'study';init_demo(root, interview=True)
            cfg=read_json(root/'study.json');cfg['is_demo']=False
            store=Store(root, read_json(root/'catalog.json'), cfg)
            calls=[]
            def request(*args):
                calls.append(args)
                if len(calls)==1: raise TimeoutError('provider unavailable')
                return {'choices':[{'finish_reason':'stop','message':{'content':'What made the source seem unclear?'}}]}
            service=Interview(store, request=request);s=store.create(True)
            payload={'video_id':s['video']['video_id'],'request_id':'recover-0001','expected_turn':0,'answer':'The source is unclear.'}
            with self.assertRaises(StudyError) as error: service.answer(s['token'],payload)
            self.assertEqual(error.exception.status,503)
            state=store.current(s['token'])['interview']
            self.assertEqual(state['answered'],1);self.assertTrue(state['pending_question'])
            self.assertEqual(state['retry_payload'],payload)
            after=service.answer(s['token'],state['retry_payload'])
            self.assertFalse(after['interview']['pending_question'])
            self.assertEqual(len(store.interview_export()),1)
            service.answer(s['token'],payload)
            self.assertEqual(len(calls),2)

    @patch.dict('os.environ', {'OPENAI_API_KEY':'test-only'})
    def test_slow_participant_does_not_block_another(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'study';init_demo(root, interview=True)
            cfg=read_json(root/'study.json');cfg['is_demo']=False
            store=Store(root,read_json(root/'catalog.json'),cfg)
            entered=threading.Event();release=threading.Event();errors=[]
            def request(url,body,headers):
                if 'slow answer' in json.dumps(body):
                    entered.set()
                    if not release.wait(8):raise TimeoutError()
                return {'choices':[{'finish_reason':'stop','message':{'content':'Which detail mattered?'}}]}
            service=Interview(store,request=request);a,b=store.create(True),store.create(True)
            def payload(s,answer):return {'video_id':s['video']['video_id'],'request_id':'thread-0001','expected_turn':0,'answer':answer}
            def slow():
                try:service.answer(a['token'],payload(a,'slow answer'))
                except Exception as e:errors.append(e)
            thread=threading.Thread(target=slow);thread.start()
            try:
                self.assertTrue(entered.wait(3))
                self.assertEqual(service.answer(b['token'],payload(b,'independent answer'))['interview']['answered'],1)
                with self.assertRaises(StudyError):service.answer(a['token'],payload(a,'slow answer'))
            finally:release.set();thread.join(5)
            self.assertEqual(errors,[])


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class MediaTests(unittest.TestCase):
    def test_reject_corrupt_file_and_allow_valid_subset(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);inputs=root/'inputs';inputs.mkdir()
            clip=Path(__file__).parents[1]/'videotrust/demo/media/demo_community.mp4'
            shutil.copy2(clip,inputs/'good.mp4');(inputs/'bad.mp4').write_bytes(b'not a video')
            with self.assertRaises(ValueError):register(root/'strict',inputs)
            self.assertFalse((root/'strict/catalog.json').exists())
            self.assertEqual(register(root/'subset',inputs,skip_invalid=True),1)
            report=read_json(root/'subset/registration_report.json')
            self.assertEqual(len(report['invalid']),1)
            self.assertEqual(inspect_media(inputs/'good.mp4')['video_codec'],'h264')

    def test_private_evidence_and_csv_match_selected_measure(self):
        try:import cv2
        except ImportError:self.skipTest('OpenCV optional')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'study';init_demo(root,paired=True)
            prepare(root,frames=2)
            server=create_server(root,port=0,admin_token='long-admin-test-token')
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}';vid=read_json(root/'catalog.json')[0]['video_id']
            def get(path,authorized=True):
                headers={'Authorization':'Bearer long-admin-test-token'} if authorized else {}
                try:
                    with urllib.request.urlopen(urllib.request.Request(base+path,headers=headers)) as r:return r.status,r.read()
                except urllib.error.HTTPError as e:return e.code,e.read()
            try:
                for path in ('/api/admin/video?id='+vid,'/api/admin/frame?id='+vid+'&index=0','/api/admin/comparison.csv'):
                    self.assertEqual(get(path,False)[0],401)
                status,body=get('/api/admin/video?id='+vid);self.assertEqual(status,200)
                detail=json.loads(body);self.assertEqual(len(detail['evidence']['frames']),2)
                frame=detail['evidence']['frames'][0];self.assertNotIn('path',frame)
                self.assertEqual(get(frame['url'])[0],200)
                self.assertEqual(get('/api/admin/frame?id='+vid+'&index=-1')[0],404)
                self.assertEqual(get('/api/admin/comparison?measure=wrong')[0],400)
                status,body=get('/api/admin/comparison.csv?measure=interview_inferred')
                self.assertEqual(status,200)
                rows=list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))))
                self.assertTrue(all(r['participant_measure']=='interview_inferred' for r in rows))
                self.assertTrue(all(r['human_mean']=='' for r in rows))
            finally:server.shutdown();server.server_close();thread.join()

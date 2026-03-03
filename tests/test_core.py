import copy
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
from pathlib import Path
from videotrust.__main__ import init_demo, register
from videotrust.common import csv_cell, digest, file_hash, read_json, write_json
from videotrust.compare import comparison
from videotrust.legacy import parse_run
from videotrust.llm import validate_result, analyze
from videotrust.server import create_server
from videotrust.storage import Store, StudyError

RESULT = {'trust_score':0,'rationale':'Limited evidence.','factors':['No external verification'],
          'full_summary':'A test clip. It contains a claim.','short_summary':'A test claim',
          'topics':['test'],'limitations':['Sparse frames']}


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'study'
        init_demo(self.path)
        self.catalog=read_json(self.path/'catalog.json')
        self.config=read_json(self.path/'study.json')
        # Three identities exercise allocation using the one bundled media fixture.
        self.catalog = [{**self.catalog[0], 'video_id': f'allocation_{i}'} for i in range(3)]
        self.config['videos_per_session'] = 3
        self.store=Store(self.path,self.catalog,self.config)

    def tearDown(self): self.tmp.cleanup()

    def test_consent_resume_allocation_and_zero(self):
        for bad in (False,None,'yes',1):
            with self.assertRaises(StudyError): self.store.create(bad)
        session=self.store.create(True)
        self.assertEqual(session['video'],self.store.current(session['token'])['video'])
        self.assertEqual(set(session['video']),{'video_id','title','media_url'})
        seen=[]
        for n in range(3):
            vid=session['video']['video_id']; seen.append(vid)
            payload={'video_id':vid,'trust_score':0,'confidence':None,'rationale':'', 'watch_seconds':0}
            after=self.store.rate(session['token'],payload)
            self.assertEqual(self.store.rate(session['token'],payload),after)
            session={**after,'token':session['token']}
        self.assertEqual(len(set(seen)),3)
        self.assertTrue(session['done'])
        self.assertEqual(len(self.store.ratings()),3)
        self.assertTrue(Store(self.path,self.catalog,self.config).current(session['token'])['done'])

    def test_input_validation_and_assignment(self):
        s=self.store.create(True); v=s['video']['video_id']
        for score in (-1,11,True,5.5,'5',float('nan')):
            with self.subTest(score=score), self.assertRaises(StudyError):
                self.store.rate(s['token'],{'video_id':v,'trust_score':score})
        with self.assertRaises(StudyError):self.store.rate(s['token'],{'video_id':'unassigned','trust_score':5})
        with self.assertRaises(StudyError):self.store.rate('bad-token',{'video_id':v,'trust_score':5})
        with self.assertRaises(StudyError):self.store.rate(s['token'],{'video_id':v,'trust_score':5,'watch_seconds':float('inf')})
        self.assertEqual(len(self.store.ratings()),0)

    def test_duplicate_conflict_and_study_freeze(self):
        s=self.store.create(True);payload={'video_id':s['video']['video_id'],'trust_score':5}
        self.store.rate(s['token'],payload)
        with self.assertRaises(StudyError):self.store.rate(s['token'],{**payload,'trust_score':7})
        changed=copy.deepcopy(self.catalog);changed[0]['title']='Changed'
        with self.assertRaises(ValueError):Store(self.path,changed,self.config)

    def test_csv_injection_escaping(self):
        for text in ('=SUM(1,1)','  @foo','+cmd','-cmd'):
            self.assertTrue(csv_cell(text).startswith("'"))
        self.assertEqual(csv_cell(-2),-2)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.path=Path(cls.tmp.name)/'demo';init_demo(cls.path)
        cls.token='test-admin-token-123456789'
        cls.server=create_server(cls.path,port=0,admin_token=cls.token)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.tmp.cleanup()

    def request(self,path,payload=None,headers=None):
        data=json.dumps(payload).encode() if payload is not None else None
        req=urllib.request.Request(self.base+path,data=data,headers={'Content-Type':'application/json',**(headers or {})})
        try:
            with urllib.request.urlopen(req) as r:return r.status,r.headers,r.read()
        except urllib.error.HTTPError as e:return e.code,e.headers,e.read()

    def test_private_routes_and_files(self):
        for path in ['/api/admin/comparison','/api/admin/export.csv']:
            self.assertEqual(self.request(path)[0],401)
        for path in ['/../responses.sqlite3','/catalog.json','/study.json','/analyses.jsonl','/.env']:
            self.assertEqual(self.request(path)[0],404)
        code,_,body=self.request('/api/admin/comparison',headers={'Authorization':'Bearer '+self.token})
        self.assertEqual(code,200);self.assertEqual(len(json.loads(body)['groups']),1)

    def test_origin_and_json_validation(self):
        self.assertEqual(self.request('/api/sessions',{'consent':True},{'Origin':'https://other.invalid'})[0],403)
        self.assertEqual(self.request('/api/sessions',[])[0],400)

    def test_media_ranges(self):
        path='/media/part_46'
        code,headers,body=self.request(path,headers={'Range':'bytes=0-99'})
        self.assertEqual(code,206);self.assertEqual(len(body),100);self.assertEqual(headers['Accept-Ranges'],'bytes')
        self.assertEqual(self.request(path,headers={'Range':'bytes=-50'})[0],206)
        self.assertEqual(self.request(path,headers={'Range':'bytes=999999999-'})[0],416)
        self.assertEqual(self.request(path,headers={'Range':'bytes=abc'})[0],416)

    def test_full_http_roundtrip(self):
        code,_,body=self.request('/api/sessions',{'consent':True});self.assertEqual(code,201)
        s=json.loads(body);header={'Authorization':'Bearer '+s['token']}
        for _ in range(s['total']):
            code,_,body=self.request('/api/ratings',{'video_id':s['video']['video_id'],'trust_score':0,'rationale':'=1+1'},header)
            self.assertEqual(code,200);s=json.loads(body)
        self.assertTrue(s['done'])
        code,_,body=self.request('/api/admin/export.csv',headers={'Authorization':'Bearer '+self.token})
        self.assertEqual(code,200);self.assertIn("'=1+1",body.decode('utf-8-sig'))


class AnalysisTests(unittest.TestCase):
    def test_collector_counts_unique_retained_videos(self):
        from videotrust.collect import collect
        calls=[]
        def response(url):
            path=urlsplit(url).path; q=parse_qs(urlsplit(url).query); calls.append((path,q))
            if path.endswith('/search'):
                ids=['aaaaaaaaaaa','aaaaaaaaaaa','bbbbbbbbbbb'] if q['regionCode'][0]=='DE' else ['ccccccccccc']
                return {'items':[{'id':{'videoId':v}} for v in ids]}
            if path.endswith('/videos'):
                if q['id'][0]=='bbbbbbbbbbb':return {'items':[]}
                return {'items':[{'snippet':{'title':q['id'][0]}}]}
            if path.endswith('/commentThreads'):
                return {'items':[{'snippet':{'topLevelComment':{'snippet':{'textDisplay':'A comment','authorDisplayName':'Private name'}}}}]}
            raise AssertionError(path)
        with tempfile.TemporaryDirectory() as td, patch.dict('os.environ',{'YOUTUBE_API_KEY':'dummy'}):
            rows,issues=collect(td,'test',['DE','FI'],limit=2,request=response)
            self.assertEqual([r['video_id'] for r in rows],['aaaaaaaaaaa','ccccccccccc'])
            self.assertEqual(issues,[])
            self.assertNotIn('Private name',json.dumps(rows))
            self.assertEqual([q['regionCode'][0] for path,q in calls if path.endswith('/search')],['DE','FI'])

    def test_model_validation(self):
        self.assertEqual(validate_result(RESULT)['trust_score'],0)
        for bad in (float('nan'),float('inf'),True,11,'5'):
            with self.assertRaises(ValueError):validate_result({**RESULT,'trust_score':bad})
        with self.assertRaises(ValueError):validate_result({**RESULT,'short_summary':'one '*11})

    def test_comparison_grouping_nulls_and_duplicates(self):
        cat=[{'video_id':str(i),'title':str(i),'media_sha256':'sha'} for i in range(3)]
        hs=[{'video_id':str(i),'trust_score':i*2} for i in range(3)]
        models=[{'video_id':str(i),'trust_score':i*2+1,'model':'test','temperature':0,'evidence_mode':'video_only','is_demo':False,'status':'ok','job_id':str(i),'media_sha256':'sha'} for i in range(3)]
        extra={**models[0],'job_id':'other','temperature':1,'trust_score':10}
        data=comparison(cat,hs,models+models+[extra])
        self.assertEqual(len(data['groups']),2)
        self.assertEqual(data['summary']['mean_absolute_gap'],1)
        self.assertEqual(data['summary']['mean_signed_gap'],-1)
        self.assertEqual(data['summary']['pearson_r'],1)
        self.assertTrue(all(r['model_n']==1 for r in data['rows']))
        self.assertIsNone(comparison(cat,[],models)['summary']['mean_absolute_gap'])
        self.assertFalse(comparison(cat,hs,[{**models[0],'media_sha256':'different'}])['groups'])

    def test_legacy_parser_conservative(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'trust_analysis_results_temp2_run2.txt'
            p.write_text('# Video Path: C:\\Videos\\clip.mp4\n**trust_score:** 6\n**why_test_score:** Explanation\n**factor_choice:** Details\n**full_summary:** Summary\n**short_summary:** Test clip\n')
            row=parse_run(p)[0]
            self.assertEqual(row['trust_score'],6)
            self.assertEqual(row['status'],'needs_review')
            self.assertIn('temperature_2_requires_manual_review',row['review_reasons'])

    def test_pipeline_offline_request_and_resume(self):
        with tempfile.TemporaryDirectory() as td:
            w=Path(td)/'study';(w/'media').mkdir(parents=True)
            (w/'media/test.mp4').write_bytes(b'test fixture')
            sha=file_hash(w/'media/test.mp4')
            write_json(w/'catalog.json',[{'video_id':'test','title':'Test','media_path':'media/test.mp4','media_sha256':sha,'comments':[{'author':'PRIVATE','comment':'hello'}]}])
            write_json(w/'study.json',{'is_demo':False})
            write_json(w/'evidence/test.json',{'video_id':'test','transcript':'Test transcript','transcription_status':'ok','frames':[],'media_sha256':sha})
            calls=[]
            def response(url,payload,headers):
                calls.append(payload)
                return {'id':'test','model':'snapshot-test','choices':[{'finish_reason':'stop','message':{'content':json.dumps(RESULT)}}]}
            self.assertEqual(analyze(w,temperatures=[0,.5],runs=2,api_key='dummy',request=response),(4,0))
            self.assertEqual(analyze(w,temperatures=[0,.5],runs=2,api_key='dummy',request=response),(0,0))
            self.assertEqual(analyze(w,temperatures=[0.0,.5],runs=2,api_key='dummy',request=response),(0,0))
            self.assertEqual(len(calls),4)
            self.assertNotIn('PRIVATE',json.dumps(calls))
            self.assertNotIn('hello',json.dumps(calls))
            self.assertEqual(analyze(w,api_key='dummy',evidence_mode='metadata_comments',request=response),(1,0))
            self.assertIn('hello',json.dumps(calls[-1]));self.assertNotIn('PRIVATE',json.dumps(calls[-1]))
            with self.assertRaises(ValueError):
                analyze(w,api_key='dummy',evidence_mode='source_context',request=response)
            catalog=read_json(w/'catalog.json')
            catalog[0]['metadata']={'source_context':{'publisher':'Named publisher','basis':'Researcher-supplied source record'}, 'likes':999}
            write_json(w/'catalog.json',catalog)
            self.assertEqual(analyze(w,api_key='dummy',evidence_mode='source_context',request=response),(1,0))
            content=json.loads(calls[-1]['messages'][1]['content'][0]['text'])
            self.assertEqual(content['researcher_supplied_source_context']['publisher'],'Named publisher')
            self.assertNotIn('comments',content);self.assertNotIn('metadata',content)
            self.assertNotIn('hello',json.dumps(content));self.assertNotIn('999',json.dumps(content))
            self.assertEqual(analyze(w,api_key='dummy',evidence_mode='source_context',request=response),(0,0))

    def test_failed_model_outputs_do_not_become_scores(self):
        with tempfile.TemporaryDirectory() as td:
            w=Path(td);(w/'media').mkdir();(w/'media/v.mp4').write_bytes(b'test')
            sha=file_hash(w/'media/v.mp4')
            write_json(w/'catalog.json',[{'video_id':'v','title':'V','media_path':'media/v.mp4','media_sha256':sha}])
            write_json(w/'study.json',{'is_demo':False})
            write_json(w/'evidence/v.json',{'video_id':'v','transcript':'x','transcription_status':'ok','frames':[],'media_sha256':sha})
            def refusal(*a):return {'choices':[{'finish_reason':'stop','message':{'refusal':'Refused'}}]}
            self.assertEqual(analyze(w,api_key='dummy',request=refusal),(0,1))
            self.assertFalse((w/'analyses.jsonl').exists())
            self.assertTrue((w/'analysis_errors.jsonl').exists())


class OptionalMediaTests(unittest.TestCase):
    def test_real_opencv_decode_when_available(self):
        try:import cv2
        except ImportError:self.skipTest('OpenCV is an optional analysis dependency')
        from videotrust.media import extract_frames
        with tempfile.TemporaryDirectory() as td:
            clip=Path(__file__).parents[1]/'videotrust/demo/media/part_46.mp4'
            duration,frames=extract_frames(clip,td,count=3)
            self.assertAlmostEqual(duration,50.9,places=1)
            self.assertEqual(len(frames),3)
            self.assertTrue(all(Path(f['path']).stat().st_size>1000 for f in frames))


if __name__=='__main__':unittest.main()

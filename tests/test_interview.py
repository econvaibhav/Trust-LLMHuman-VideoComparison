import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from videotrust.__main__ import init_demo
from videotrust.common import read_json, write_json
from videotrust.interview import Interview, validate_inference
from videotrust.storage import Store, StudyError


class InterviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'study'
        init_demo(self.path, interview=True)
        self.cfg = read_json(self.path / 'study.json')
        self.catalog = read_json(self.path / 'catalog.json')

    def tearDown(self):
        self.tmp.cleanup()

    def service(self, live=False, request=None):
        self.cfg['is_demo'] = not live
        self.store = Store(self.path, self.catalog, self.cfg)
        return Interview(self.store, **({'request': request} if request else {}))

    def payload(self, session, turn=0, answer='I found the source unclear.'):
        return {'video_id': session['video']['video_id'], 'expected_turn': turn,
                'request_id': f'request-{turn:04d}', 'answer': answer}

    def test_demo_resume_retry_and_no_score_leak(self):
        service = self.service()
        s = self.store.create(True)
        p = self.payload(s)
        after = service.answer(s['token'], p)
        self.assertEqual(after['interview']['answered'], 1)
        self.assertEqual(service.answer(s['token'], p), after)
        self.assertNotIn('trust_score', json.dumps(after))
        self.assertEqual(self.store.current(s['token']), after)
        with self.assertRaises(StudyError):
            service.answer(s['token'], {**p, 'answer': 'Changed'})
        for turn in (1, 2):
            after = service.answer(s['token'], self.payload(s, turn))
        self.assertEqual(after['completed'], 1)
        self.assertNotEqual(after['video']['video_id'], s['video']['video_id'])
        self.assertEqual(len(self.store.participant_rows()), 1)
        self.assertEqual(self.store.participant_rows()[0]['measure'], 'interview_inferred')
        self.assertEqual(len(self.store.interview_export()), 3)
        self.assertEqual(service.answer(s['token'], self.payload(s, 2)), after)
        with self.assertRaises(StudyError):
            self.store.rate(s['token'], {'video_id': after['video']['video_id'], 'trust_score': 5})

    def test_early_finish_and_session_isolation(self):
        service = self.service()
        s = self.store.create(True)
        with self.assertRaises(StudyError):
            service.answer(s['token'], {**self.payload(s), 'answer': ''}, finish=True)
        service.answer(s['token'], self.payload(s))
        other = self.store.create(True)
        self.assertEqual(self.store.current(other['token'])['interview']['answered'], 0)
        after = service.answer(s['token'], {'video_id': s['video']['video_id'], 'request_id': 'finish-0001'}, finish=True)
        self.assertEqual(after['completed'], 1)
        self.assertEqual(len(self.store.interview_export()), 1)

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only'})
    def test_live_contract_final_failure_preserves_answers_and_can_retry(self):
        calls = []
        failing = [True]
        def request(url, body, headers):
            calls.append(body)
            if 'response_format' not in body:
                content = 'What evidence supported your impression?'
            elif failing[0]:
                return {'choices': [{'finish_reason': 'length', 'message': {'content': '{'}}]}
            else:
                content = json.dumps({'trust_score': None, 'rationale': 'Insufficient evidence.',
                                      'participant_summary': 'The participant is unsure.', 'factors': []})
            return {'model': 'test-snapshot', 'choices': [{'finish_reason': 'stop', 'message': {'content': content}}]}
        service = self.service(live=True, request=request)
        s = self.store.create(True)
        for turn in (0, 1):
            service.answer(s['token'], self.payload(s, turn))
        with self.assertRaises(StudyError) as exc:
            service.answer(s['token'], self.payload(s, 2))
        self.assertEqual(exc.exception.status, 503)
        self.assertEqual(len(self.store.interview_export()), 3)
        self.assertEqual(self.store.participant_rows(), [])
        self.assertTrue(self.store.current(s['token'])['interview']['ready_to_finish'])
        failing[0] = False
        after = service.answer(s['token'], self.payload(s, 2))
        self.assertEqual(after['completed'], 1)
        self.assertIsNone(self.store.participant_rows()[0]['trust_score'])
        self.assertEqual(len(self.store.interview_export()), 3)
        self.assertNotIn('media_url', json.dumps(calls))

    def test_invalid_inference(self):
        for value in (True, 11, float('nan')):
            with self.assertRaises(ValueError):
                validate_inference({'trust_score': value, 'rationale': 'Reason', 'participant_summary': 'Summary', 'factors': []})

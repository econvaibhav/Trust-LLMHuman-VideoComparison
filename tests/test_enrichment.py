import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from videotrust.common import file_hash, read_json, write_json
from videotrust.llm import analyze


class EnrichmentTests(unittest.TestCase):
    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only'})
    def test_summary_sentiment_topics_and_text_only_analysis(self):
        try:
            import sklearn
            import vaderSentiment
        except ImportError:
            self.skipTest('Optional enrichment dependencies')
        from videotrust.enrich import enrich
        with tempfile.TemporaryDirectory() as td:
            w = Path(td)
            (w / 'media').mkdir()
            catalog = []
            for i in range(2):
                vid = f'video_{i}'
                media = w / f'media/{vid}.mp4'
                media.write_bytes(bytes([i]))
                sha = file_hash(media)
                catalog.append({'video_id': vid, 'title': vid, 'media_path': f'media/{vid}.mp4',
                                'media_sha256': sha, 'comments': [{'comment': 'Awful fake content', 'author': 'PRIVATE'}]})
                write_json(w / f'evidence/{vid}.json', {'video_id': vid, 'media_sha256': sha,
                           'transcript': f'Transcript {i}', 'transcription_status': 'ok', 'frames': []})
            write_json(w / 'catalog.json', catalog)
            write_json(w / 'study.json', {'is_demo': False})
            calls = []
            def request(url, body, headers):
                calls.append(body)
                if url.endswith('/embeddings'):
                    return {'data': [{'index': 1, 'embedding': [0, 1]}, {'index': 0, 'embedding': [1, 0]}]}
                if body['response_format']['json_schema']['name'] == 'video_context':
                    result = {'visual_summary': 'A short test clip.', 'classification': 'Interview', 'limitations': ['Sparse frames']}
                else:
                    result = {'trust_score': 4, 'rationale': 'Limited evidence', 'factors': ['Presentation'],
                              'full_summary': 'A test clip. It makes a claim.', 'short_summary': 'Test claim',
                              'topics': ['test'], 'limitations': ['Text only']}
                return {'model': 'test-snapshot', 'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(result)}}]}
            self.assertEqual(enrich(w, clusters=2, request=request), (2, []))
            self.assertEqual(len(calls), 3)
            self.assertEqual(enrich(w, clusters=2, request=request), (2, []))
            self.assertEqual(len(calls), 3)
            context = read_json(w / 'context/video_0.json')
            self.assertLess(context['comments'][0]['comment_sentiment']['compound'], 0)
            self.assertIn(context['topic'], ('Topic 0', 'Topic 1'))
            self.assertEqual(analyze(w, evidence_mode='legacy_enriched', api_key='test-only', request=request), (2, 0))
            self.assertNotIn('PRIVATE', json.dumps(calls))
            self.assertEqual(len(calls[-1]['messages'][1]['content']), 1)
            self.assertIn('visual_summary', calls[-1]['messages'][1]['content'][0]['text'])
            ev = read_json(w / 'evidence/video_0.json'); ev['transcript'] = 'Changed'
            write_json(w / 'evidence/video_0.json', ev)
            with self.assertRaises(ValueError):
                analyze(w, evidence_mode='legacy_enriched', api_key='test-only', request=request)

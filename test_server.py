import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from server import Handler, validate_lead

VALID = {'name': 'Alex Demo', 'email': 'alex@example.com', 'category': 'website',
         'message': 'A fictional website integration enquiry.'}


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        Handler.attempts.clear()

    def request(self, method='POST', path='/api/leads', body=None, content_type='application/json'):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        payload = json.dumps(VALID) if body is None else body
        connection.request(method, path, body=payload if method == 'POST' else None,
                           headers={'Content-Type': content_type})
        response = connection.getresponse()
        status, headers, body = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return status, headers, body

    def test_success_is_preview_only(self):
        status, headers, body = self.request()
        data = json.loads(body)
        self.assertEqual(status, 201)
        self.assertFalse(data['notification']['sent'])
        self.assertEqual(data['notification']['payload']['chat_id'], 'DEMO_CHAT_ID')
        self.assertEqual(data['notification']['mode'], 'preview_only')
        self.assertIn('alex@example.com', data['notification']['payload']['text'])
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_invalid_fields_rejected(self):
        for changed in [{'email': 'bad'}, {'name': ' '}, {'message': 'short'},
                        {'category': 'unknown'}, {'email': 12}, {'name': 'A\nB'},
                        {'name': 'a' * 81}, {'message': 'x' * 1501}]:
            with self.subTest(changed=changed):
                data = dict(VALID, **changed)
                self.assertEqual(self.request(body=json.dumps(data))[0], 400)

    def test_unknown_and_missing_fields_rejected(self):
        for data in [dict(VALID, secret='not-needed'), {'name': 'Alex'}, [], None]:
            with self.subTest(data=data):
                self.assertEqual(self.request(body=json.dumps(data))[0], 400)

    def test_malformed_json_and_utf8(self):
        self.assertEqual(self.request(body='{')[0], 400)
        self.assertEqual(self.request(body=b'\xff')[0], 400)

    def test_oversize_request_rejected(self):
        self.assertEqual(self.request(body='x' * 8193)[0], 413)

    def test_non_json_rejected(self):
        self.assertEqual(self.request(content_type='text/plain')[0], 415)

    def test_no_file_or_lead_listing(self):
        for path in ['/api/leads', '/server.py', '/.env', '/../server.py']:
            with self.subTest(path=path):
                self.assertEqual(self.request(method='GET', path=path)[0], 404)

    def test_static_ui_and_health(self):
        for path in ['/', '/style.css', '/app.js', '/api/health']:
            with self.subTest(path=path):
                self.assertEqual(self.request(method='GET', path=path)[0], 200)

    def test_rate_limit(self):
        for _ in range(20):
            self.assertEqual(self.request()[0], 201)
        self.assertEqual(self.request()[0], 429)

    def test_trims_fields(self):
        self.assertEqual(validate_lead(dict(VALID, name=' Alex Demo '))['name'], 'Alex Demo')


if __name__ == '__main__':
    unittest.main()

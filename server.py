"""Local portfolio demo. No outbound messaging or durable personal-data storage."""
import json
import re
import time
import uuid
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
MAX_BODY = 8192
CATEGORIES = {'website', 'ecommerce', 'integration', 'automation'}


def validate_lead(data):
    if not isinstance(data, dict):
        raise ValueError('Expected a JSON object.')
    allowed = {'name', 'email', 'category', 'message'}
    if set(data) != allowed:
        raise ValueError('Provide exactly name, email, category, and message.')
    if any(not isinstance(data[key], str) for key in allowed):
        raise ValueError('All fields must be text.')
    lead = {key: data[key].strip() for key in allowed}
    for key, low, high in [('name', 1, 80), ('email', 3, 160), ('message', 10, 1500)]:
        if not low <= len(lead[key]) <= high:
            raise ValueError('{} must contain {}–{} characters.'.format(key, low, high))
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', lead['email']):
        raise ValueError('Enter a valid email address.')
    if any(ord(char) < 32 for key in ('name', 'email') for char in lead[key]):
        raise ValueError('Name and email cannot contain control characters.')
    if lead['category'] not in CATEGORIES:
        raise ValueError('Choose a supported project category.')
    return lead


def create_demo_response(lead):
    lead_id = 'DEMO-' + uuid.uuid4().hex[:8].upper()
    text = 'New demo enquiry {}\nName: {}\nEmail: {}\nCategory: {}\nMessage: {}'.format(
        lead_id, lead['name'], lead['email'], lead['category'], lead['message'])
    return {
        'id': lead_id,
        'status': 'validated',
        'notification': {
            'mode': 'preview_only',
            'sent': False,
            'method': 'sendMessage',
            'payload': {'chat_id': 'DEMO_CHAT_ID', 'text': text},
        },
        'notice': 'Demo only: no Telegram message was sent and no lead was stored.',
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    attempts = defaultdict(deque)
    rate_lock = Lock()

    def log_message(self, *_args):
        # Request bodies and contact fields are never logged.
        return

    def send_body(self, status, body, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def respond(self, status, data):
        self.send_body(status, json.dumps(data, ensure_ascii=False).encode(), 'application/json; charset=utf-8')

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/health':
            return self.respond(200, {'ok': True, 'mode': 'demo', 'telegram': 'preview_only'})
        files = {'/': ('index.html', 'text/html'), '/index.html': ('index.html', 'text/html'),
                 '/style.css': ('style.css', 'text/css'), '/app.js': ('app.js', 'text/javascript')}
        if path not in files:
            return self.respond(404, {'error': 'Not found.'})
        filename, mime = files[path]
        self.send_body(200, (ROOT / filename).read_bytes(), mime + '; charset=utf-8')

    def do_POST(self):
        # Close after POST, including rejected bodies, to prevent unread-body reuse.
        self.close_connection = True
        if urlsplit(self.path).path != '/api/leads':
            return self.respond(404, {'error': 'Not found.'})
        if self.headers.get('Transfer-Encoding'):
            return self.respond(400, {'error': 'Transfer encoding is unsupported.'})
        content_type = self.headers.get('Content-Type', '').split(';')[0].strip().lower()
        if content_type != 'application/json':
            return self.respond(415, {'error': 'Use application/json.'})
        try:
            length = int(self.headers.get('Content-Length', ''))
        except ValueError:
            return self.respond(411, {'error': 'A valid Content-Length is required.'})
        if length < 1 or length > MAX_BODY:
            return self.respond(413, {'error': 'JSON body must be 1–8192 bytes.'})
        now = time.monotonic()
        with self.rate_lock:
            recent = self.attempts[self.client_address[0]]
            while recent and now - recent[0] >= 60:
                recent.popleft()
            if len(recent) >= 20:
                return self.respond(429, {'error': 'Demo limit: 20 attempts per minute. Try again shortly.'})
            recent.append(now)
        try:
            raw = self.rfile.read(length)
            lead = validate_lead(json.loads(raw))
        except (ValueError, UnicodeDecodeError) as exc:
            return self.respond(400, {'error': str(exc) if not isinstance(exc, json.JSONDecodeError) else 'Invalid JSON.'})
        return self.respond(201, create_demo_response(lead))

    def setup(self):
        super().setup()
        self.connection.settimeout(10)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print('LeadFlow demo: http://127.0.0.1:{}'.format(server.server_port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

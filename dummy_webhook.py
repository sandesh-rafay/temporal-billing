from http.server import HTTPServer, BaseHTTPRequestHandler
import json

PORT = 5678


class WebhookHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            event = json.loads(body)
            print(f"\n--- Event received ---")
            print(json.dumps(event, indent=2))
        except json.JSONDecodeError:
            print(f"\n--- Raw payload (not JSON) ---")
            print(body.decode())

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format, *args):
        pass  # suppress default per-request access logs


print(f"Dummy webhook listening on port {PORT}...")
print(f"Events will be printed here as they arrive.")
HTTPServer(("0.0.0.0", PORT), WebhookHandler).serve_forever()

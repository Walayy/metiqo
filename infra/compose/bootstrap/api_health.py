"""Serveur de santé temporaire utilisé avant le ticket FastAPI FND-007."""

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from metiquo.config import load_settings


class HealthHandler(BaseHTTPRequestHandler):
    """Exposer uniquement l'état du conteneur bootstrap."""

    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        payload = json.dumps({"status": "ok", "phase": "bootstrap"}).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def main() -> None:
    """Valider la configuration puis écouter pour les healthchecks Docker."""

    load_settings()
    server = ThreadingHTTPServer(("0.0.0.0", 8000), HealthHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()

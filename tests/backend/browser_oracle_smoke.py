"""Exercise the real Oracle export browser against loopback with --network none."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from metiquo_core.config import Settings
from metiquo_worker.archive import SourceFile
from metiquo_worker.sources.oracle import export_url


def main():
    expected = "https://storage.googleapis.com/drive-bulk-export-anonymous/synthetic.zip"
    files = [SourceFile(str(year), f"{year}_test.csv", year) for year in (2025, 2026)]
    rows = "".join(f'<div role="row" aria-selected="false">{item.name}</div>' for item in files)
    html = (
        '<div role="grid">'
        + rows
        + '</div><button role="menuitem">Download</button><div id="result"></div>'
        + """<script>
        const rows = [...document.querySelectorAll('[role=row]')];
        rows.forEach(row => {
          row.onclick = event => {
            if (!event.ctrlKey) rows.forEach(other => other.setAttribute('aria-selected', 'false'));
            row.setAttribute('aria-selected', 'true');
          };
          row.oncontextmenu = event => event.preventDefault();
        });
        document.querySelector('button').onclick = () => {
          const anchor = document.createElement('a');
          anchor.href = '"""
        + expected
        + """';
          anchor.textContent = 'Synthetic archive';
          document.querySelector('#result').append(anchor);
        };
        </script>"""
    ).encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    class LocalSettings(Settings):
        @property
        def oracle_folder_url(self) -> str:
            return f"http://127.0.0.1:{server.server_port}/folder"

    try:
        result = export_url(LocalSettings(database_url="postgresql://unused"), files)
        assert result == expected
        print("PASS: Oracle launches installed full Chromium, selects files and observes export")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()

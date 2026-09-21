"""Offline browser smoke test, run explicitly in a container with --network none.

Uses only a loopback HTTP server, a temporary browser profile and synthetic data.
It does not launch the worker service, connect to PostgreSQL or visit SofaScore.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace

from metiquo_core.config import Settings
from metiquo_worker.sofascore_policy import SofaScoreBlocked
from metiquo_worker.sources import sofascore


def main():
    counts = {"script": 0, "refused": 0, "after": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            status = 200
            if self.path == "/shared.js":
                counts["script"] += 1
                body = b"document.documentElement.dataset.loaded = 'yes';"
                mime, cache = "text/javascript", "public, max-age=600"
            elif self.path == "/refusal":
                counts["refused"] += 1
                body, mime, cache, status = b"Forbidden", "text/plain", "no-store", 403
            elif self.path == "/after":
                counts["after"] += 1
                body, mime, cache = b"must not be requested", "text/plain", "no-store"
            else:
                body = (
                    b'<html><head><script src="/shared.js"></script></head>'
                    b"<body><button onclick=\"fetch('/refusal').then(() => "
                    b"setTimeout(() => fetch('/after'), 1000))\">"
                    b"Request refusal</button></body></html>"
                )
                mime, cache = "text/html", "no-store"
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Cache-Control", cache)
            self.send_header("Content-Length", str(len(body)))
            if self.path == "/one":
                self.send_header("Set-Cookie", "test-profile=kept; Max-Age=3600; SameSite=Lax")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    observe = sofascore._observe_response

    def local_observer(response):
        if response.status == 403:
            # Preserve the real status/type but give the observer its source host.
            # The actual request and response remain on loopback, never on SofaScore.
            observe(
                SimpleNamespace(
                    url="https://www.sofascore.com/api/v1/synthetic-refusal",
                    status=response.status,
                    headers=response.headers,
                    request=response.request,
                )
            )
        else:
            observe(response)

    try:
        with TemporaryDirectory() as profile:
            settings = Settings(
                database_url="postgresql://unused",
                sofascore_browser_profile_dir=profile,
            )
            sofascore._observe_response = local_observer
            page = sofascore._browser_page(settings)
            context = sofascore._BROWSER.context
            for document in ("one", "two", "three"):
                assert sofascore._browser_page(settings) is page
                assert sofascore._BROWSER.context is context
                page.goto(root + "/" + document, wait_until="load")
                assert page.locator("html").get_attribute("data-loaded") == "yes"
                sofascore.idle_browser()
            assert counts["script"] == 1, counts
            sofascore._close_browser()
            page = sofascore._browser_page(settings)
            page.goto(root + "/four", wait_until="load")
            assert counts["script"] == 1, counts
            assert "test-profile=kept" in page.evaluate("document.cookie")
            assert len(sofascore._BROWSER.context.pages) == 1
            try:
                page.get_by_role("button", name="Request refusal").click()
                page.wait_for_timeout(500)
            except Exception:
                assert sofascore._BLOCK_ERROR is not None
            assert isinstance(sofascore._BLOCK_ERROR, SofaScoreBlocked)
            assert sofascore._BLOCK_ERROR.status == 403
            assert counts == {"script": 1, "refused": 1, "after": 0}, counts
            assert sofascore._BROWSER.page is None
            assert not sofascore._BROWSER.context.pages
            try:
                sofascore._browser_page(settings)
            except SofaScoreBlocked:
                pass
            else:
                raise AssertionError("Refused cycle restarted the browser page")
            sofascore._close_browser()
            print(
                "PASS: one context, persistent cookie/cache, first 403 closes page and stops cycle"
            )
    finally:
        sofascore._close_browser()
        sofascore._BLOCK_ERROR = None
        sofascore._observe_response = observe
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()

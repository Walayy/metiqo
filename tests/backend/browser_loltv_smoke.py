"""Run in the worker image with --network none; all routes are synthetic.

Exercises the actual DOM reader and first-refusal cleanup in full Chromium.
Never contacts LoLTV. No source observation is published to a database.
"""

import json
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace

from metiquo_core.config import Settings
from metiquo_worker import loltv_browser
from metiquo_worker.loltv_policy import LoltvBlocked
from metiquo_worker.sources.loltv import ROOT_URL, detail, listing
from patchright.sync_api import sync_playwright

fixtures = Path(__file__).parent / "fixtures/loltv"
events, _, _ = listing((fixtures / "matches.html").read_text(), ROOT_URL)
event = next(item for item in events if "skillcamp" in item.url)
source = (fixtures / "detail.html").read_text()
event = detail(source, event)
roles = ["TOP", "JUNGLE", "MID", "BOTTOM", "SUPPORT"]
transport = (
    "a:"
    + json.dumps(
        [{"role": roles[i % 5], "player": {"summoner_name": f"player{i}"}} for i in range(10)]
    )
    + "\n"
)
page_html = (
    re.sub(r"<img[^>]*>", "", source).replace(
        "</main>",
        """
<section><h2>Game stats</h2><p>12:34</p>
<button aria-label="Select the match game" onclick="options.hidden=false">Game 3</button>
<div id="options" hidden>
<button role="option" onclick="choose(1)">Game 1 16.18</button>
<button role="option" onclick="choose(2)">Game 2 16.18</button>
<button role="option" onclick="choose(3)">Game 3 16.18</button>
</div><p id="loading"></p><div id="stats"></div></section></main>
""",
    )
    + "<script>self.__next_f=self.__next_f||[];self.__next_f.push("
    + json.dumps([1, transport])
    + ")</script>"
    + """
<script>
function render(number) {
  const champ = ['Ahri','Gnar','Ashe'][number-1];
  stats.innerHTML = ['Skillcamp','Arctic Pandas'].map((name,team)=>
    '<div><div><span class="truncate">'+name+'</span><p>3 Towers</p></div><ul>'+
    Array.from({length:5}, (_,i)=>'<li><p>player'+(team*5+i)+'</p>'+
    '<a href="/stats/champion/'+champ+'"><img alt="'+champ+'">18</a>'+
    '<p>'+number+' / 2 / 3</p><p>100 CS</p><p>+4000</p></li>').join('')+'</ul></div>'
  ).join('');
}
function choose(number) {
  document.querySelector('button[aria-label]').textContent='Game '+number;
  options.hidden=true; loading.textContent='Connecting …';
  setTimeout(()=>{render(number);loading.textContent='';},350);
}
render(3);
</script>
"""
)


class Policy:
    def __init__(self):
        self.refused = []

    def check(self):
        pass

    def before_request(self, wait=None):
        pass

    def browser_request(self):
        pass

    def record_traffic(self, traffic):
        self.traffic = traffic

    def page_completed(self):
        pass

    def block(self, status, reason, retry_after=None, **kwargs):
        self.refused.append({"status": status, "reason": reason, **kwargs})
        return LoltvBlocked("synthetic refusal", status=status, retry_at=123)


def run():
    with tempfile.TemporaryDirectory() as directory, sync_playwright() as runtime:
        browser = runtime.chromium.launch(channel="chromium", headless=True)
        settings = Settings(
            database_url="postgresql+psycopg://unused/unused_test",
            artifact_dir=Path(directory),
            loltv_timeout_seconds=5,
        )
        try:
            for refusal in (None, 403, 429):
                context = browser.new_context()
                requests = []

                def route(request, _incoming, requests=requests, refusal=refusal):
                    requests.append(request.request.url)
                    if refusal == 403 or "/synthetic-refusal" in request.request.url:
                        request.fulfill(
                            status=refusal, body="refused", headers={"Retry-After": "900"}
                        )
                    else:
                        body = page_html
                        if refusal == 429:
                            body += '<script>fetch("/synthetic-refusal");</script>'
                        request.fulfill(status=200, body=body, content_type="text/html")

                context.route("**/*", route)
                loltv_browser._LOCAL.browser = SimpleNamespace(context=context, close=context.close)
                policy = Policy()
                try:
                    result = loltv_browser.render_details(event, source, settings, policy, {})
                    assert refusal is None
                    maps = result.payload["rendered"]["maps"]
                    assert [m["sides"][0]["players"][0]["champion"] for m in maps] == [
                        "Ahri",
                        "Gnar",
                        "Ashe",
                    ]
                    assert all(len(s["players"]) == 5 for m in maps for s in m["sides"])
                    assert all(s["side"] is None for m in maps for s in m["sides"])
                    assert all(
                        p["gold"] is None for m in maps for s in m["sides"] for p in s["players"]
                    )
                    assert len(requests) == 1
                except LoltvBlocked as error:
                    assert refusal == error.status
                    assert len(policy.refused) == 1
                    assert policy.refused[0]["resource_type"] == (
                        "document" if refusal == 403 else "fetch"
                    )
                    assert not context.pages
                    assert len(requests) == (1 if refusal == 403 else 2)
                finally:
                    loltv_browser.close_browser()
        finally:
            browser.close()
    print("PASS: current game DOM, stale connecting guard, unknown gold/sides, 403/429 stop")


if __name__ == "__main__":
    run()

import threading
from unittest.mock import Mock

from metiquo_core.config import Settings
from metiquo_worker import cli


def test_catalog_failure_does_not_prevent_due_oracle_collection(monkeypatch):
    stopping = threading.Event()
    monkeypatch.setattr(cli.threading, "Event", lambda: stopping)
    monkeypatch.setattr(cli.signal, "signal", lambda *_: None)
    monkeypatch.setattr(cli, "catalog_due", lambda *_: True)
    monkeypatch.setattr(cli, "due_scope", lambda *_: (True, False))
    catalog = Mock(side_effect=RuntimeError("Catalog unavailable"))
    calls = []

    def collect(*args, **kwargs):
        calls.append(kwargs)
        stopping.set()

    monkeypatch.setattr(cli, "sync_catalog", catalog)
    monkeypatch.setattr(cli, "collect", collect)
    cli.serve(Mock(), Settings(database_url="postgresql://unused"))
    assert catalog.call_count == 1
    assert calls == [{"latest": True}]

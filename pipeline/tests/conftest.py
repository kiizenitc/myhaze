import pytest


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch):
    """Retries and DOE politeness pauses must not slow the test suite."""
    monkeypatch.setattr("myhaze.http.time.sleep", lambda seconds: None)

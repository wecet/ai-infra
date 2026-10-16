import httpx
import pytest
from services.agent_polling import reconnect


def test_permanent_error_is_not_retried():
    calls = []
    def operation():
        calls.append(1)
        httpx.Response(403, request=httpx.Request('GET', 'http://agent')).raise_for_status()
    with pytest.raises(httpx.HTTPStatusError): reconnect(operation, lambda _: None)
    assert len(calls) == 1


def test_outage_is_bounded(monkeypatch):
    import services.agent_polling as polling
    ticks = iter([0, 0, 3, 3])
    monkeypatch.setenv('AGENT_RECONNECT_SECONDS', '1')
    monkeypatch.setattr(polling.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(polling.time, 'sleep', lambda _: None)
    with pytest.raises(TimeoutError):
        reconnect(lambda: (_ for _ in ()).throw(httpx.ConnectError('offline')), lambda _: None)

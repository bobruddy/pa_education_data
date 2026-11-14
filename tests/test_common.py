"""PDE downloads retry a dropped handshake."""

import requests

from pa_edu.common import http_get


def test_http_get_retries_a_dropped_handshake(monkeypatch) -> None:
    calls = {"n": 0}

    class Response:
        content = b"ok"

        def raise_for_status(self) -> None:
            return None

    def get(url: str, headers: dict, timeout: tuple[int, int]) -> Response:
        calls["n"] += 1
        assert timeout == (20, 180)
        if calls["n"] == 1:
            raise requests.ConnectTimeout("timed out")
        return Response()

    monkeypatch.setattr("pa_edu.common.requests.get", get)
    monkeypatch.setattr("pa_edu.common.time.sleep", lambda _seconds: None)
    assert http_get("https://www.pa.gov/x").content == b"ok"
    assert calls["n"] == 2

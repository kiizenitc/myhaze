import httpx
import pytest

from myhaze.http import FetchError, get_json, make_client


def client_for(handler):
    return make_client(transport=httpx.MockTransport(handler))


def test_get_json_retries_until_success():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, json={"ok": True})

    assert get_json(client_for(handler), "https://x.test/a") == {"ok": True}
    assert len(calls) == 3


def test_get_json_retries_on_html_instead_of_json():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, text="<html>maintenance</html>")
        return httpx.Response(200, json=[1])

    assert get_json(client_for(handler), "https://x.test/a") == [1]


def test_get_json_error_hides_url_and_query():
    def handler(request):
        return httpx.Response(500)

    with pytest.raises(FetchError) as info:
        get_json(client_for(handler), "https://x.test/api/SECRETPATH/data",
                 params={"token": "SECRET123"}, label="FIRMS area")
    message = str(info.value)
    assert message == "FIRMS area failed after 3 attempts: HTTP 500"
    assert info.value.__cause__ is None and info.value.__suppress_context__


def test_get_json_defaults_label_to_host():
    with pytest.raises(FetchError) as info:
        get_json(client_for(lambda r: httpx.Response(404)), "https://x.test/feed/@1/?token=abc")
    assert str(info.value) == "x.test failed after 3 attempts: HTTP 404"


def test_requests_carry_the_myhaze_user_agent():
    seen = {}

    def handler(request):
        seen["ua"] = request.headers["user-agent"]
        return httpx.Response(200, json={})

    get_json(client_for(handler), "https://x.test/")
    assert seen["ua"].startswith("MYHaze/0.1")

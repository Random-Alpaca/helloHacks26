import pytest

from hub.site import NotLoggedIn, get_all, next_link


def test_next_link():
    h = '<https://x/api/courses?page=2>; rel="next", <https://x/api/courses?page=1>; rel="first"'
    assert next_link(h) == "https://x/api/courses?page=2"
    assert next_link('<x>; rel="last"') is None
    assert next_link(None) is None


class FakeResponse:
    def __init__(self, status, body="[]", link=None):
        self.status = status
        self.ok = status < 400
        self.headers = {"link": link} if link else {}
        self._body = body

    def text(self):
        return self._body


class FakeRequestContext:
    """Queues canned responses per call, ignoring the URL."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        return self.responses.pop(0)


def test_get_all_follows_pagination():
    req = FakeRequestContext([
        FakeResponse(200, "[1, 2]", link='<https://x/y?page=2>; rel="next"'),
        FakeResponse(200, "[3]"),
    ])
    assert get_all(req, "https://x/y", {"per_page": 100}) == [1, 2, 3]
    assert len(req.calls) == 2


def test_get_all_raises_on_expired_session():
    req = FakeRequestContext([FakeResponse(401)])
    with pytest.raises(NotLoggedIn):
        get_all(req, "https://x/y", {})

"""The dev reverse proxy that puts /web and /app behind the api's one public URL."""

import httpx2
import pytest
from app.api.v1 import web_proxy
from app.main import app
from fastapi.testclient import TestClient

_REAL_ASYNC_CLIENT = httpx2.AsyncClient


@pytest.fixture
def upstream(monkeypatch):
    """Replace the proxy's outbound client with one that answers from a handler and
    records what it was asked, so no dev server needs to be running."""
    seen: list[httpx2.Request] = []
    reply = {"status": 200, "headers": {}, "content": b"<html>upstream</html>"}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(reply["status"], headers=reply["headers"], content=reply["content"])

    def factory(*args, **kwargs):
        return _REAL_ASYNC_CLIENT(*args, transport=httpx2.MockTransport(handler), **kwargs)

    monkeypatch.setattr(web_proxy.httpx2, "AsyncClient", factory)
    return type("Upstream", (), {"seen": seen, "reply": reply})


@pytest.fixture
def proxy():
    return TestClient(app)


def test_web_goes_to_the_customer_app_with_path_and_query_intact(proxy, upstream):
    r = proxy.get("/web/new/abc123?x=1&y=two")
    assert r.status_code == 200
    assert r.text == "<html>upstream</html>"
    assert str(upstream.seen[0].url) == "http://frontend-customer:5174/web/new/abc123?x=1&y=two"


def test_app_goes_to_the_dashboard(proxy, upstream):
    proxy.get("/app/approvals")
    assert str(upstream.seen[0].url) == "http://frontend:5173/app/approvals"


@pytest.mark.parametrize("path", ["/web", "/web/", "/app", "/app/"])
def test_bare_and_trailing_slash_routes_are_proxied_too(proxy, upstream, path):
    assert proxy.get(path).status_code == 200
    assert len(upstream.seen) == 1


def test_method_and_body_are_forwarded(proxy, upstream):
    proxy.post("/web/anything", content=b"payload-bytes", headers={"Content-Type": "text/plain"})
    request = upstream.seen[0]
    assert request.method == "POST"
    assert request.content == b"payload-bytes"


def test_the_incoming_host_header_is_not_forwarded(proxy, upstream):
    """The upstream dev server is addressed by its own name; passing the caller's Host through
    would break Vite's allowedHosts check."""
    proxy.get("/web/x")
    assert upstream.seen[0].headers["host"] == "frontend-customer:5174"


def test_upstream_status_and_headers_come_back_without_hop_by_hop_ones(proxy, upstream):
    upstream.reply.update(status=404, headers={"x-from-vite": "yes", "connection": "keep-alive"}, content=b"nope")
    r = proxy.get("/web/missing")
    assert r.status_code == 404
    assert r.text == "nope"
    assert r.headers["x-from-vite"] == "yes"
    assert "keep-alive" not in r.headers.get("connection", "")


def test_redirects_are_returned_to_the_caller_not_followed(proxy, upstream):
    upstream.reply.update(status=302, headers={"location": "/web/login"}, content=b"")
    r = proxy.get("/web/old", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/web/login"
    assert len(upstream.seen) == 1

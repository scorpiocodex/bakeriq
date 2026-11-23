"""The Twilio Content API client, exercised against an in-memory transport (no network)."""

import base64
import json

import httpx2
import pytest
from app.services.twilio_content_service import (
    CONTENT_API_BASE_URL,
    QuickReplyAction,
    TwilioContentClient,
    TwilioContentError,
    UrlAction,
)

SID, TOKEN = "ACtest", "secret-token"


def make_client(handler):
    http = httpx2.Client(transport=httpx2.MockTransport(handler))
    return TwilioContentClient(account_sid=SID, auth_token=TOKEN, http_client=http)


def json_response(status, body):
    return httpx2.Response(status, json=body)


def test_create_quick_reply_posts_the_expected_payload_and_returns_the_sid():
    seen = {}

    def handler(request):
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        return json_response(201, {"sid": "HX111"})

    client = make_client(handler)
    sid = client.create_quick_reply(
        friendly_name="bakeriq_nav",
        body="What next?",
        actions=[QuickReplyAction(title="Reorder", id="reorder"), QuickReplyAction(title="New", id="new")],
        variables={"1": "name"},
    )
    assert sid == "HX111"
    assert seen["url"] == f"{CONTENT_API_BASE_URL}/Content"
    assert seen["body"]["friendly_name"] == "bakeriq_nav"
    assert seen["body"]["variables"] == {"1": "name"}
    assert seen["body"]["types"]["twilio/quick-reply"]["actions"] == [
        {"title": "Reorder", "id": "reorder"},
        {"title": "New", "id": "new"},
    ]
    expected = "Basic " + base64.b64encode(f"{SID}:{TOKEN}".encode()).decode()
    assert seen["auth"] == expected


def test_create_call_to_action_builds_url_buttons():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return json_response(201, {"sid": "HX222"})

    sid = make_client(handler).create_call_to_action(
        friendly_name="bakeriq_cart_link",
        body="Open your cart",
        actions=[UrlAction(title="Open cart", url="https://example.test/web/new/{{1}}")],
    )
    assert sid == "HX222"
    assert seen["body"]["types"]["twilio/call-to-action"]["actions"] == [
        {"type": "URL", "title": "Open cart", "url": "https://example.test/web/new/{{1}}"}
    ]
    assert "variables" not in seen["body"]


def test_button_count_limits_are_enforced_before_any_request():
    client = make_client(lambda request: pytest.fail("no request should be made"))
    with pytest.raises(ValueError):
        client.create_quick_reply(friendly_name="x", body="b", actions=[])
    with pytest.raises(ValueError):
        client.create_quick_reply(
            friendly_name="x", body="b", actions=[QuickReplyAction(title=str(i), id=str(i)) for i in range(4)]
        )
    with pytest.raises(ValueError):
        client.create_call_to_action(friendly_name="x", body="b", actions=[])


def test_an_error_status_raises_with_the_status_and_body():
    client = make_client(lambda request: httpx2.Response(400, text="bad template"))
    with pytest.raises(TwilioContentError) as exc:
        client.create_quick_reply(friendly_name="x", body="b", actions=[QuickReplyAction(title="a", id="a")])
    assert "400" in str(exc.value) and "bad template" in str(exc.value)


def test_a_response_without_a_sid_is_an_error():
    client = make_client(lambda request: json_response(201, {"unexpected": True}))
    with pytest.raises(TwilioContentError):
        client.create_quick_reply(friendly_name="x", body="b", actions=[QuickReplyAction(title="a", id="a")])


def test_list_templates_follows_the_next_page_url():
    pages = {
        None: {"contents": [{"sid": "HX1", "friendly_name": "a"}], "meta": {"next_page_url": f"{CONTENT_API_BASE_URL}/Content?Page=1"}},
        "1": {"contents": [{"sid": "HX2", "friendly_name": "b"}], "meta": {"next_page_url": None}},
    }

    def handler(request):
        return json_response(200, pages[request.url.params.get("Page")])

    assert [t["sid"] for t in make_client(handler).list_templates()] == ["HX1", "HX2"]


def test_find_by_friendly_name_returns_the_sid_or_none():
    body = {"contents": [{"sid": "HX1", "friendly_name": "a"}, {"sid": "HX2", "friendly_name": "b"}], "meta": {}}
    client = make_client(lambda request: json_response(200, body))
    assert client.find_by_friendly_name("b") == "HX2"
    assert client.find_by_friendly_name("missing") is None


def test_get_template_returns_json_and_raises_on_404():
    ok = make_client(lambda request: json_response(200, {"sid": "HX1"}))
    assert ok.get_template("HX1") == {"sid": "HX1"}
    missing = make_client(lambda request: httpx2.Response(404, text="not found"))
    with pytest.raises(TwilioContentError):
        missing.get_template("HX404")


def test_delete_is_idempotent_for_404_but_not_for_other_errors():
    make_client(lambda request: httpx2.Response(204)).delete_template("HX1")
    make_client(lambda request: httpx2.Response(404)).delete_template("HX1")
    with pytest.raises(TwilioContentError):
        make_client(lambda request: httpx2.Response(500, text="boom")).delete_template("HX1")


def test_the_default_client_is_built_and_closed_by_the_wrapper():
    client = TwilioContentClient(account_sid=SID, auth_token=TOKEN)
    assert isinstance(client._http, httpx2.Client)
    client.close()
    assert client._http.is_closed

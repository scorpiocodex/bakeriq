"""Tests for app.services.whatsapp_sender — Twilio REST outbound helpers.

Four entry points:
  send_text       Plain-text WhatsApp message
  send_template   Content Template message (interactive buttons)
  send_reply      Dispatches on Reply shape to one of the above
  send_replies    Sends multiple Replies in order; returns SID list

All four log every send attempt to conversation_messages — success OR
failure — so the audit trail is complete. The Twilio call itself is
the boundary we mock; the conversation log call goes through real DB.

Test strategy:
  - Patch the Twilio client at the import point in whatsapp_sender
  - Use the real db_session fixture so the audit log write is verified
    against actual SQL
  - Cover happy path (SID returned, log written), Twilio failure
    (None returned, log still written), and the dispatching logic in
    send_reply / send_replies
"""

from unittest.mock import MagicMock, patch

import pytest
from app.models.conversation import Conversation, ConversationMessage
from app.models.customer import Customer
from app.services import whatsapp_sender
from app.services.reply import Reply
from sqlalchemy import select
from twilio.base.exceptions import TwilioRestException

PHONE = "+919888777111"
FROM_WHATSAPP = "whatsapp:+14155238886"  # Twilio sandbox sender


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def customer(db_session):
    c = Customer(
        name="Sender Test",
        primary_phone=PHONE,
        whatsapp_enabled=True,
        is_active=True,
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture
def conversation(db_session, customer):
    conv = Conversation(
        customer_id=customer.id,
        phone=customer.primary_phone,
    )
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    return conv


def _make_twilio_mock(sid: str = "SM_test_sid") -> MagicMock:
    """Build a Twilio client mock whose messages.create() returns a
    MagicMock with the given .sid attribute. The real Twilio SDK
    returns a MessageInstance with .sid as a property; we just need
    the attribute access to work."""
    client = MagicMock()
    msg = MagicMock()
    msg.sid = sid
    client.messages.create.return_value = msg
    return client


def _make_twilio_rest_exception(code: int = 63016, msg: str = "test failure"):
    """Construct a TwilioRestException with realistic fields. The real
    exception constructor in the installed Twilio SDK requires
    (status, uri, msg, code, method) — `status` is the HTTP status,
    `code` is the Twilio-specific code (e.g. 63038 for quota exceeded).
    The whatsapp_sender except block reads .code and .msg from it.

    Note: the SDK signature has shifted across versions; the keyword
    list here matches the currently installed twilio package."""
    return TwilioRestException(
        status=400,
        uri="/2010-04-01/Accounts/AC_test/Messages.json",
        msg=msg,
        code=code,
        method="POST",
    )


# ============================================================
# send_text
# ============================================================


class TestSendText:
    @patch("app.services.whatsapp_sender.get_twilio_client")
    def test_returns_sid_on_success(self, mock_get_client, db_session, conversation):
        mock_get_client.return_value = _make_twilio_mock(sid="SM_ok")

        sid = whatsapp_sender.send_text(
            db_session,
            conversation_id=conversation.id,
            to_phone=PHONE,
            body="hello world",
        )

        assert sid == "SM_ok"

    @patch("app.services.whatsapp_sender.get_twilio_client")
    def test_logs_outbound_on_success(self, mock_get_client, db_session, conversation):
        """The audit log row must capture the body and the returned SID."""
        mock_get_client.return_value = _make_twilio_mock(sid="SM_ok")

        whatsapp_sender.send_text(
            db_session,
            conversation_id=conversation.id,
            to_phone=PHONE,
            body="hello world",
        )
        db_session.commit()  # flush from the service is local; commit for our SELECT

        msg = db_session.scalar(
            select(ConversationMessage).where(
                ConversationMessage.conversation_id == conversation.id
            )
        )
        assert msg is not None
        assert msg.direction == "outbound"
        assert msg.body == "hello world"
        assert msg.twilio_sid == "SM_ok"

    @patch("app.services.whatsapp_sender.get_twilio_client")
    def test_returns_none_on_twilio_failure(
        self, mock_get_client, db_session, conversation
    ):
        """A TwilioRestException (rate limit, quota, sandbox not joined,
        etc.) should NOT propagate. send_text returns None instead."""
        client = MagicMock()
        client.messages.create.side_effect = _make_twilio_rest_exception()
        mock_get_client.return_value = client

        sid = whatsapp_sender.send_text(
            db_session,
            conversation_id=conversation.id,
            to_phone=PHONE,
            body="hello",
        )

        assert sid is None

    @patch("app.services.whatsapp_sender.get_twilio_client")
    def test_logs_outbound_on_failure(self, mock_get_client, db_session, conversation):
        """Even when Twilio rejects the send, we still write an audit
        row — twilio_sid will be None, signaling the attempt failed."""
        client = MagicMock()
        client.messages.create.side_effect = _make_twilio_rest_exception()
        mock_get_client.return_value = client

        whatsapp_sender.send_text(
            db_session,
            conversation_id=conversation.id,
            to_phone=PHONE,
            body="goodbye",
        )
        db_session.commit()

        msg = db_session.scalar(
            select(ConversationMessage).where(
                ConversationMessage.conversation_id == conversation.id
            )
        )
        assert msg is not None
        assert msg.body == "goodbye"
        assert msg.twilio_sid is None

    @patch("app.services.whatsapp_sender.get_twilio_client")
    def test_normalizes_phone_to_whatsapp_address(
        self, mock_get_client, db_session, conversation
    ):
        """Plain phone string should get the whatsapp: prefix when sent
        to Twilio. Sending without the prefix would be rejected."""
        mock_client = _make_twilio_mock()
        mock_get_client.return_value = mock_client

        whatsapp_sender.send_text(
            db_session,
            conversation_id=conversation.id,
            to_phone="+911234567890",
            body="hello",
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["to"] == "whatsapp:+911234567890"

    @patch("app.services.whatsapp_sender.get_twilio_client")
    def test_preserves_existing_whatsapp_prefix(
        self, mock_get_client, db_session, conversation
    ):
        """If the caller already gave us a whatsapp: prefixed address,
        don't double-prefix."""
        mock_client = _make_twilio_mock()
        mock_get_client.return_value = mock_client

        whatsapp_sender.send_text(
            db_session,
            conversation_id=conversation.id,
            to_phone="whatsapp:+911234567890",
            body="hello",
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["to"] == "whatsapp:+911234567890"


# ============================================================
# send_template
# ============================================================


class TestSendTemplate:
    @patch("app.services.whatsapp_sender.get_twilio_client")
    def test_sends_template_with_content_sid(
        self, mock_get_client, db_session, conversation
    ):
        mock_client = _make_twilio_mock(sid="MM_tmpl")
        mock_get_client.return_value = mock_client

        sid = whatsapp_sender.send_template(
            db_session,
            conversation_id=conversation.id,
            to_phone=PHONE,
            content_sid="HX_test_sid",
        )

        assert sid == "MM_tmpl"
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["content_sid"] == "HX_test_sid"
        # When no variables provided, the kwarg should be absent
        assert "content_variables" not in call_kwargs

    @patch("app.services.whatsapp_sender.get_twilio_client")
    def test_content_variables_serialized_as_json_string(
        self, mock_get_client, db_session, conversation
    ):
        """Twilio's REST API expects ContentVariables as a JSON-encoded
        string, not a dict. The SDK doesn't auto-serialize. The
        wrapper must do it."""
        import json

        mock_client = _make_twilio_mock()
        mock_get_client.return_value = mock_client

        whatsapp_sender.send_template(
            db_session,
            conversation_id=conversation.id,
            to_phone=PHONE,
            content_sid="HX_test",
            content_variables={"1": "Anita", "2": "tok_xyz"},
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "content_variables" in call_kwargs
        # Should be a string we can JSON-decode back to the dict
        decoded = json.loads(call_kwargs["content_variables"])
        assert decoded == {"1": "Anita", "2": "tok_xyz"}

    @patch("app.services.whatsapp_sender.get_twilio_client")
    def test_logs_with_supplied_log_body(
        self, mock_get_client, db_session, conversation
    ):
        """log_body argument should be the body recorded in the audit
        log — gives the admin transcript viewer something readable
        rather than a raw SID."""
        mock_get_client.return_value = _make_twilio_mock(sid="MM_x")

        whatsapp_sender.send_template(
            db_session,
            conversation_id=conversation.id,
            to_phone=PHONE,
            content_sid="HX_x",
            log_body="Hi Anita! How can we help today?",
        )
        db_session.commit()

        msg = db_session.scalar(
            select(ConversationMessage).where(
                ConversationMessage.conversation_id == conversation.id
            )
        )
        assert msg.body == "Hi Anita! How can we help today?"

    @patch("app.services.whatsapp_sender.get_twilio_client")
    def test_falls_back_to_structured_log_body(
        self, mock_get_client, db_session, conversation
    ):
        """If log_body isn't supplied, the audit log should still get a
        useful identifier — at minimum the SID. The exact format is
        flexible but it must include the SID so an admin can match
        the log entry back to the template that was sent."""
        mock_get_client.return_value = _make_twilio_mock(sid="MM_x")

        whatsapp_sender.send_template(
            db_session,
            conversation_id=conversation.id,
            to_phone=PHONE,
            content_sid="HX_special_template",
            content_variables={"1": "value"},
        )
        db_session.commit()

        msg = db_session.scalar(
            select(ConversationMessage).where(
                ConversationMessage.conversation_id == conversation.id
            )
        )
        assert "HX_special_template" in msg.body

    @patch("app.services.whatsapp_sender.get_twilio_client")
    def test_returns_none_and_logs_on_twilio_failure(
        self, mock_get_client, db_session, conversation
    ):
        client = MagicMock()
        client.messages.create.side_effect = _make_twilio_rest_exception(
            code=63038, msg="exceeded daily limit"
        )
        mock_get_client.return_value = client

        sid = whatsapp_sender.send_template(
            db_session,
            conversation_id=conversation.id,
            to_phone=PHONE,
            content_sid="HX_x",
            log_body="quota test",
        )
        db_session.commit()

        assert sid is None
        msg = db_session.scalar(
            select(ConversationMessage).where(
                ConversationMessage.conversation_id == conversation.id
            )
        )
        assert msg is not None
        assert msg.body == "quota test"
        assert msg.twilio_sid is None


# ============================================================
# send_reply (dispatcher)
# ============================================================


class TestSendReply:
    """send_reply inspects the Reply shape and dispatches to the right
    underlying send method. We verify the dispatching by mocking the
    Twilio client and checking which API call was made."""

    @patch("app.services.whatsapp_sender.get_twilio_client")
    def test_text_reply_routes_to_send_text(
        self, mock_get_client, db_session, conversation
    ):
        mock_client = _make_twilio_mock(sid="SM_text")
        mock_get_client.return_value = mock_client

        sid = whatsapp_sender.send_reply(
            db_session,
            conversation_id=conversation.id,
            to_phone=PHONE,
            reply=Reply.text("hello"),
        )

        assert sid == "SM_text"
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["body"] == "hello"
        assert "content_sid" not in call_kwargs

    @patch("app.services.whatsapp_sender.get_twilio_client")
    def test_template_reply_routes_to_send_template(
        self, mock_get_client, db_session, conversation
    ):
        mock_client = _make_twilio_mock(sid="MM_tmpl")
        mock_get_client.return_value = mock_client

        sid = whatsapp_sender.send_reply(
            db_session,
            conversation_id=conversation.id,
            to_phone=PHONE,
            reply=Reply.template("HX_test", variables={"1": "Anita"}),
        )

        assert sid == "MM_tmpl"
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["content_sid"] == "HX_test"
        assert "body" not in call_kwargs


# ============================================================
# send_replies (list dispatcher)
# ============================================================


class TestSendReplies:
    """send_replies sends a list of Replies in order and returns the SID
    list. Failures show up as None entries; the function does NOT raise
    even if Twilio rejects one or more sends."""

    @patch("app.services.whatsapp_sender.get_twilio_client")
    def test_sends_all_replies_in_order(
        self, mock_get_client, db_session, conversation
    ):
        # Each .create call returns a fresh sid; track call order
        client = MagicMock()
        client.messages.create.side_effect = [
            MagicMock(sid="SM_first"),
            MagicMock(sid="SM_second"),
        ]
        mock_get_client.return_value = client

        sids = whatsapp_sender.send_replies(
            db_session,
            conversation_id=conversation.id,
            to_phone=PHONE,
            replies=[
                Reply.text("first message"),
                Reply.template("HX_test"),
            ],
        )

        assert sids == ["SM_first", "SM_second"]
        assert client.messages.create.call_count == 2

    @patch("app.services.whatsapp_sender.get_twilio_client")
    def test_partial_failure_returns_mixed_sids(
        self, mock_get_client, db_session, conversation
    ):
        """First send succeeds, second fails → ['SM_x', None].
        Critical for the parse_and_send classifier to report honestly."""
        client = MagicMock()
        client.messages.create.side_effect = [
            MagicMock(sid="SM_ok"),
            _make_twilio_rest_exception(),
        ]
        mock_get_client.return_value = client

        sids = whatsapp_sender.send_replies(
            db_session,
            conversation_id=conversation.id,
            to_phone=PHONE,
            replies=[
                Reply.text("succeeded"),
                Reply.text("will fail"),
            ],
        )

        assert sids == ["SM_ok", None]

    @patch("app.services.whatsapp_sender.get_twilio_client")
    def test_empty_list_returns_empty_list(
        self, mock_get_client, db_session, conversation
    ):
        """Defensive: an empty list shouldn't crash or call Twilio at all."""
        sids = whatsapp_sender.send_replies(
            db_session,
            conversation_id=conversation.id,
            to_phone=PHONE,
            replies=[],
        )

        assert sids == []
        mock_get_client.assert_not_called()

    @patch("app.services.whatsapp_sender.get_twilio_client")
    def test_logs_every_reply_attempt(self, mock_get_client, db_session, conversation):
        """Two replies in, two audit rows out — regardless of send
        success. This is the audit guarantee the original docstrings
        promise."""
        client = MagicMock()
        client.messages.create.side_effect = [
            MagicMock(sid="SM_one"),
            _make_twilio_rest_exception(),
        ]
        mock_get_client.return_value = client

        whatsapp_sender.send_replies(
            db_session,
            conversation_id=conversation.id,
            to_phone=PHONE,
            replies=[
                Reply.text("body one"),
                Reply.text("body two"),
            ],
        )
        db_session.commit()

        rows = db_session.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
            .order_by(ConversationMessage.created_at)
        ).all()
        assert len(rows) == 2
        assert rows[0].body == "body one"
        assert rows[0].twilio_sid == "SM_one"
        assert rows[1].body == "body two"
        assert rows[1].twilio_sid is None

"""Tests for the registration handler — bot logic for the new-customer flow."""

import pytest

from app.services import pending_registration_service as pr_svc
from app.services.registration_handler import (
    MSG_AWAITING_APPROVAL,
    MSG_GREETING_NEW,
    MSG_REJECTED,
    MSG_STILL_AWAITING,
    handle_registration_message,
)


PHONE = "+919888777111"  # fake number, no collision with seed customers


@pytest.fixture(autouse=True)
def cleanup_pending(db_session):
    """Remove any pending row for our test phone, before and after each test."""
    existing = pr_svc.get_pending_by_phone(db_session, PHONE)
    if existing:
        db_session.delete(existing)
        db_session.commit()
    yield
    existing = pr_svc.get_pending_by_phone(db_session, PHONE)
    if existing:
        db_session.delete(existing)
        db_session.commit()


def test_first_contact_creates_pending_row_and_asks_name(db_session):
    reply = handle_registration_message(db_session, PHONE, "hi")
    db_session.commit()

    assert reply == MSG_GREETING_NEW
    reg = pr_svc.get_pending_by_phone(db_session, PHONE)
    assert reg is not None, "first inbound should create a pending row"
    assert reg.conversation_state == pr_svc.SUBSTATE_COLLECTING_NAME
    assert reg.status == "pending"


def test_name_then_area_advances_to_awaiting_approval(db_session):
    handle_registration_message(db_session, PHONE, "hi")
    db_session.commit()

    reply2 = handle_registration_message(db_session, PHONE, "Anita Menon")
    db_session.commit()
    assert "Anita" in reply2

    reg = pr_svc.get_pending_by_phone(db_session, PHONE)
    assert reg is not None
    assert reg.name == "Anita Menon"
    assert reg.conversation_state == pr_svc.SUBSTATE_COLLECTING_AREA

    reply3 = handle_registration_message(db_session, PHONE, "MG Road, Kochi")
    db_session.commit()
    assert reply3 == MSG_AWAITING_APPROVAL

    reg = pr_svc.get_pending_by_phone(db_session, PHONE)
    assert reg is not None
    assert reg.area == "MG Road, Kochi"
    assert reg.conversation_state == pr_svc.SUBSTATE_AWAITING_APPROVAL


def test_messages_after_awaiting_approval_get_stonewalled(db_session):
    handle_registration_message(db_session, PHONE, "hi")
    handle_registration_message(db_session, PHONE, "Anita")
    handle_registration_message(db_session, PHONE, "MG Road")
    db_session.commit()

    reply = handle_registration_message(db_session, PHONE, "any update?")
    db_session.commit()
    assert reply == MSG_STILL_AWAITING


def test_rejected_registration_blocks_further_attempts(db_session):
    handle_registration_message(db_session, PHONE, "hi")
    handle_registration_message(db_session, PHONE, "Anita")
    handle_registration_message(db_session, PHONE, "MG Road")
    db_session.commit()

    reg = pr_svc.get_pending_by_phone(db_session, PHONE)
    assert reg is not None
    pr_svc.reject(db_session, reg)
    db_session.commit()

    reply = handle_registration_message(db_session, PHONE, "please try again")
    db_session.commit()
    assert reply == MSG_REJECTED


def test_empty_name_re_prompts(db_session):
    handle_registration_message(db_session, PHONE, "hi")
    db_session.commit()

    reply = handle_registration_message(db_session, PHONE, "   ")
    db_session.commit()
    assert reply == MSG_GREETING_NEW

    reg = pr_svc.get_pending_by_phone(db_session, PHONE)
    assert reg is not None
    assert reg.conversation_state == pr_svc.SUBSTATE_COLLECTING_NAME

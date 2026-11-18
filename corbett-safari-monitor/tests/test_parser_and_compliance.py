"""Tests for raw-vs-interpreted availability parsing, access-gate detection, and read-only guard."""

from __future__ import annotations

import pytest

from src.collector import (
    ReadOnlyGuard,
    ReadOnlyViolationError,
    first_blocking_gate,
    inspect_visible_gates,
    parse_availability_text,
)


@pytest.mark.parametrize("placeholder", [None, "", "   ", "--", "N/A", "Loading..."])
def test_parser_stores_null_for_missing_placeholders(placeholder: str | None) -> None:
    res = parse_availability_text(placeholder, unit_validated=True)
    assert res.available_slots is None
    assert res.collection_status == "missing"
    assert res.raw_displayed_value == placeholder


def test_parser_distinguishes_closed_not_open_and_sold_out() -> None:
    closed = parse_availability_text("Closed for Monsoon", unit_validated=True)
    assert closed.available_slots is None
    assert closed.collection_status == "zone_closed"

    not_open = parse_availability_text("Booking Not Opened", unit_validated=True)
    assert not_open.available_slots is None
    assert not_open.collection_status == "window_not_open"

    sold_out = parse_availability_text("Sold Out", raw_capacity="30", unit_validated=True)
    assert sold_out.available_slots == 0
    assert sold_out.total_capacity == 30
    assert sold_out.collection_status == "success"
    assert sold_out.confidence == "verified"


@pytest.mark.parametrize(
    "bad_input",
    [
        "₹ 3380",
        "Rs. 3000",
        "INR 1500",
        "-4 Available",
        "12.5 slots",
        "2026-12-15",
        "75% full",
        "35 / 30",
        "99999",
        "Call Ramnagar office 9759363344",
    ],
)
def test_parser_rejects_incorrect_or_ambiguous_values_while_preserving_raw(bad_input: str) -> None:
    res = parse_availability_text(bad_input, unit_validated=True)
    assert res.available_slots is None
    assert res.collection_status == "parse_error"
    assert res.confidence == "low"
    assert res.raw_displayed_value == bad_input
    assert res.error_details is not None


def test_parser_marks_unverified_confidence_until_units_confirmed() -> None:
    unverified = parse_availability_text("18 Available", unit_validated=False)
    assert unverified.available_slots == 18
    assert unverified.total_capacity is None
    assert unverified.collection_status == "success"
    assert unverified.confidence == "unverified"

    verified_frac = parse_availability_text("18 / 30 permits", unit_validated=True)
    assert verified_frac.available_slots == 18
    assert verified_frac.total_capacity == 30
    assert verified_frac.confidence == "verified"


def test_gate_detector_catches_visible_location_and_pause_but_ignores_hidden_modals() -> None:
    # Visible location gate from safari.corbettgov.org
    loc_html = """
    <html><body>
      <div class="modal active">
        <h3>Location verification required</h3>
        <p>To protect your account and meet regulatory requirements, we must verify your location before you can continue.</p>
      </div>
    </body></html>
    """
    blocker = first_blocking_gate(inspect_visible_gates(html=loc_html))
    assert blocker is not None
    assert blocker.gate_type == "location_verification_required"

    # Hidden inactive modals in SPA shell must NOT produce false-positive blocks
    clean_with_hidden_modals = """
    <html><body>
      <div style="display: none;">Location verification required</div>
      <div hidden>All bookings have been paused by the department!</div>
      <main><h2>Bijrani</h2><span>Morning: 14 / 30</span></main>
    </body></html>
    """
    assert first_blocking_gate(inspect_visible_gates(html=clean_with_hidden_modals)) is None

    # HTTP 403 / IP block
    http_block = first_blocking_gate(inspect_visible_gates(html="", http_status=403))
    assert http_block is not None
    assert http_block.gate_type == "ip_or_access_restricted"


def test_read_only_guard_blocks_booking_and_payment_interactions() -> None:
    ReadOnlyGuard.assert_safe_url(
        "https://safari.corbettgov.org/", allowed_hosts={"safari.corbettgov.org"}
    )
    with pytest.raises(ReadOnlyViolationError):
        ReadOnlyGuard.assert_safe_url(
            "https://safari.corbettgov.org/checkout", allowed_hosts={"safari.corbettgov.org"}
        )
    with pytest.raises(ReadOnlyViolationError):
        ReadOnlyGuard.assert_safe_interaction_label("button:has-text('Pay Now')")
    assert ReadOnlyGuard.should_block_network_request("https://api.razorpay.com/v1/orders", "POST")
    assert ReadOnlyGuard.should_block_network_request("https://safari.corbettgov.org/api/book", "POST")
    assert not ReadOnlyGuard.should_block_network_request("https://safari.corbettgov.org/", "GET")

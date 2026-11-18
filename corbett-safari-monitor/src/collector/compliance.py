"""Compliance checks, visible access-gate detection, and strict read-only safeguards.

Grounded directly in Phase 1 inspection of https://safari.corbettgov.org/ and
https://corbettgov.org/terms:
- Never bypass consent notices, browser location verification, CAPTCHA, clock checks,
  departmental pause screens, authentication, or IP restrictions.
- Never submit forms, enter passenger data, add permits to cart, or touch payment flows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag


@dataclass(frozen=True)
class AccessGateFinding:
    """Represents a blocking gate or informational notice found on the visible page."""

    gate_type: str
    is_blocking: bool
    message: str
    matched_text: str


# Keywords/paths that MUST NEVER be navigated to, clicked, or submitted by a read-only monitor.
FORBIDDEN_BOOKING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bpay\s*now\b", re.IGNORECASE),
    re.compile(r"\bproceed\s+to\s+pay\b", re.IGNORECASE),
    re.compile(r"\brazorpay\b", re.IGNORECASE),
    re.compile(r"\bcheckout\b", re.IGNORECASE),
    re.compile(r"\bconfirm\s+booking\b", re.IGNORECASE),
    re.compile(r"\breserve\s+permit\b", re.IGNORECASE),
    re.compile(r"\badd\s+to\s+cart\b", re.IGNORECASE),
    re.compile(r"\bvisitor\s+details\b", re.IGNORECASE),
    re.compile(r"\bpassenger\s+details\b", re.IGNORECASE),
    re.compile(r"\bsend\s+otp\b", re.IGNORECASE),
    re.compile(r"\bverify\s+otp\b", re.IGNORECASE),
    re.compile(r"\bupload\b.*\bid\b", re.IGNORECASE),
)

FORBIDDEN_URL_SEGMENTS: tuple[str, ...] = (
    "/checkout",
    "/payment",
    "/pay",
    "/razorpay",
    "/cart",
    "/reserve",
    "/confirm",
    "/otp",
    "/passenger",
    "/visitor-details",
)

# Gates that a human operator sitting at a local headed browser can legitimately resolve
# (e.g. clicking the browser's genuine 'Allow' location prompt) without any bypass.
HUMAN_RESOLVABLE_GATE_TYPES: frozenset[str] = frozenset({"location_verification_required"})

# Explicit mutating endpoints blocked on POST / PUT / PATCH / DELETE so the collector
# can NEVER create an order, add to cart, hold a permit, send an OTP, submit passenger
# data, or initiate payment — while NEVER aborting GET scripts/styles/assets or initial
# read-only SPA boot requests (which previously caused safari.corbettgov.org to stick on
# "Loading..." when <script src="https://checkout.razorpay.com/..."> was aborted).
_MUTATING_BOOKING_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"/(?:create|place|confirm|submit|complete)[-_]?(?:order|booking|payment|ticket)", re.IGNORECASE),
    re.compile(r"/(?:orders?|bookings?)/(?:create|place|confirm|submit)", re.IGNORECASE),
    re.compile(r"/book(?:/|$)", re.IGNORECASE),
    re.compile(r"/book[-_]?ticket", re.IGNORECASE),
    re.compile(r"/(?:add[-_]?to[-_]?cart|cart/(?:add|create|update|checkout))", re.IGNORECASE),
    re.compile(r"/(?:checkout|payment|verify[-_]?payment|pay[-_]?now)(?:/|$)", re.IGNORECASE),
    re.compile(r"/(?:reserve|hold[-_]?(?:seat|permit|slot|ticket))(?:/|$)", re.IGNORECASE),
    re.compile(r"/(?:send[-_]?otp|verify[-_]?otp|otp/(?:send|verify))(?:/|$)", re.IGNORECASE),
    re.compile(r"/(?:passenger|visitor[-_]?details)(?:/(?:add|save|create|submit)|$)", re.IGNORECASE),
)

_PAYMENT_GATEWAY_HOSTS: tuple[str, ...] = (
    "razorpay.com",
    "payu.in",
    "payumoney.com",
    "cashfree.com",
    "ccavenue.com",
    "billdesk.com",
    "paytm.com",
)
# Note from Phase 1 inspection: safari.corbettgov.org ships hidden modal markup in
# initial HTML, so callers MUST strip hidden DOM nodes before matching.
# Blocking gates checked against VISIBLE page text only.
BLOCKING_GATE_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "location_verification_required",
        re.compile(
            r"location\s+verification\s+required|verify\s+your\s+location\s+before\s+you\s+can\s+continue",
            re.IGNORECASE,
        ),
        (
            "Official portal requires browser location verification before displaying availability. "
            "Collection stopped without bypassing. Grant genuine browser location permission in a "
            "local headed session if authorized."
        ),
    ),
    (
        "portal_paused",
        re.compile(
            r"all\s+bookings\s+have\s+been\s+paused\s+by\s+the\s+department|"
            r"system\s+is\s+undergoing\s+schedules?\s+updates",
            re.IGNORECASE,
        ),
        (
            "Official portal displays a departmental pause / scheduled maintenance notice. "
            "Collection stopped cleanly and will wait for the next scheduled window."
        ),
    ),
    (
        "clock_skew",
        re.compile(
            r"set\s+time\s+automatically.*also\s+check\s+the\s+year\s+is\s+right",
            re.IGNORECASE | re.DOTALL,
        ),
        (
            "Official portal flagged a system clock/timezone mismatch. "
            "Ensure host OS NTP time sync and timezone are accurate before retrying."
        ),
    ),
    (
        "captcha_required",
        re.compile(
            r"verify\s+you\s+are\s+human|complete\s+the\s+captcha|g-recaptcha|hcaptcha|cf-turnstile",
            re.IGNORECASE,
        ),
        "Portal presented a CAPTCHA / human-verification challenge. Collection halted without bypass.",
    ),
    (
        "authentication_required",
        re.compile(
            r"sign\s+in\s+to\s+continue|login\s+required|enter\s+otp\s+to\s+view",
            re.IGNORECASE,
        ),
        "Portal requested authentication/OTP. Collection halted without bypass.",
    ),
    (
        "ip_or_access_restricted",
        re.compile(
            r"access\s+denied|403\s+forbidden|ip\s+based\s+restrictions|"
            r"your\s+ip\s+has\s+been\s+(blocked|restricted)|rate\s+limit\s+exceeded",
            re.IGNORECASE,
        ),
        (
            "Portal returned an access/IP restriction notice (see corbettgov.org/terms Clause 10 "
            "and /ipranges). Collection halted immediately."
        ),
    ),
)

INFORMATIONAL_NOTICE_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "tourist_instructions_notice",
        re.compile(r"mobile\s+phone\s+restriction\s*[–-]\s*corbett\s+tiger\s+reserve", re.IGNORECASE),
        "Visible tourist instructions notice detected on portal entry.",
    ),
    (
        "consent_notice",
        re.compile(
            r"by\s+proceeding,\s+you\s+agree\s+that\s+all\s+purchases\s+are\s+non-refundable",
            re.IGNORECASE,
        ),
        "Visible non-refundable policy/consent notice detected on portal entry.",
    ),
    (
        "monsoon_window_notice",
        re.compile(r"during\s+monsoon\s+season,\s+booking\s+window\s+will\s+open\s+only\s+for\s+t\s*\+\s*7", re.IGNORECASE),
        "Visible monsoon T+7 booking window advisory detected.",
    ),
)


def _is_element_hidden(tag: Tag) -> bool:
    """Return True if an HTML element is explicitly marked hidden via attributes or inline CSS."""
    if tag.has_attr("hidden"):
        return True
    aria_hidden = str(tag.get("aria-hidden", "")).strip().lower()
    if aria_hidden == "true":
        return True
    style = str(tag.get("style", "")).lower().replace(" ", "")
    if "display:none" in style or "visibility:hidden" in style or "opacity:0" in style:
        return True
    classes = {c.lower() for c in (tag.get("class") or [])}
    if classes & {"hidden", "d-none", "is-hidden", "modal-hidden", "sr-only"}:
        return True
    return False


def extract_visible_text_from_html(html: str) -> str:
    """Extract human-visible text from an HTML document, ignoring hidden modal containers."""
    soup = BeautifulSoup(html or "", "html.parser")
    for non_visual in soup(["script", "style", "noscript", "template"]):
        non_visual.decompose()

    # Collect hidden elements first before decomposing so tree iteration stays safe
    hidden_tags = [
        tag for tag in soup.find_all(True) if isinstance(tag, Tag) and _is_element_hidden(tag)
    ]
    for tag in hidden_tags:
        tag.decompose()

    return " ".join(soup.get_text(separator=" ").split())


def inspect_visible_gates(
    *,
    visible_text: str | None = None,
    html: str | None = None,
    http_status: int | None = None,
) -> list[AccessGateFinding]:
    """Detect blocking access controls and informational notices on the current page."""
    findings: list[AccessGateFinding] = []

    if http_status in {401, 403, 429}:
        findings.append(
            AccessGateFinding(
                gate_type="ip_or_access_restricted",
                is_blocking=True,
                message=f"Portal returned HTTP {http_status}; halting collection without bypass.",
                matched_text=f"HTTP {http_status}",
            )
        )
        return findings

    if http_status is not None and http_status >= 500:
        findings.append(
            AccessGateFinding(
                gate_type="server_unavailable",
                is_blocking=True,
                message=f"Portal returned HTTP {http_status} (temporary server failure).",
                matched_text=f"HTTP {http_status}",
            )
        )
        return findings

    text = visible_text if visible_text is not None else extract_visible_text_from_html(html or "")

    for gate_type, pattern, explanation in BLOCKING_GATE_RULES:
        match = pattern.search(text)
        if match:
            findings.append(
                AccessGateFinding(
                    gate_type=gate_type,
                    is_blocking=True,
                    message=explanation,
                    matched_text=match.group(0)[:120],
                )
            )

    for notice_type, pattern, explanation in INFORMATIONAL_NOTICE_RULES:
        match = pattern.search(text)
        if match:
            findings.append(
                AccessGateFinding(
                    gate_type=notice_type,
                    is_blocking=False,
                    message=explanation,
                    matched_text=match.group(0)[:120],
                )
            )

    return findings


def first_blocking_gate(findings: list[AccessGateFinding]) -> AccessGateFinding | None:
    """Return the first blocking `AccessGateFinding`, or `None` if access is clear."""
    for finding in findings:
        if finding.is_blocking:
            return finding
    return None


class ReadOnlyViolationError(RuntimeError):
    """Raised when any collector instruction attempts to cross the read-only boundary."""


class ReadOnlyGuard:
    """Hard safety fence preventing any booking, reservation, cart, OTP, or payment action."""

    @staticmethod
    def assert_safe_url(url: str, allowed_hosts: set[str] | None = None) -> None:
        parsed = urlparse(url)
        if parsed.scheme in {"file", "about"}:
            return
        if parsed.scheme not in {"https", "http"}:
            raise ReadOnlyViolationError(f"Blocked unsupported URL scheme: {url!r}")
        if allowed_hosts and parsed.hostname and parsed.hostname.lower() not in allowed_hosts:
            raise ReadOnlyViolationError(
                f"Blocked navigation outside official portal host ({parsed.hostname!r})"
            )
        lowered_path = (parsed.path or "").lower()
        for forbidden in FORBIDDEN_URL_SEGMENTS:
            if lowered_path == forbidden or lowered_path.startswith(f"{forbidden}/"):
                raise ReadOnlyViolationError(
                    f"Read-only guard blocked booking/payment path {parsed.path!r}"
                )

    @staticmethod
    def assert_safe_interaction_label(label_or_selector: str) -> None:
        for pattern in FORBIDDEN_BOOKING_PATTERNS:
            if pattern.search(label_or_selector or ""):
                raise ReadOnlyViolationError(
                    f"Read-only guard blocked interaction matching booking action: {label_or_selector!r}"
                )

    @staticmethod
    def should_block_network_request(
        url: str,
        method: str,
        resource_type: str | None = None,
    ) -> bool:
        """Return True ONLY when a request attempts a real booking/cart/OTP/payment mutation.

        IMPORTANT: Never aborts static page resources (`script`, `stylesheet`, `image`,
        `font`) or passive `GET`/`HEAD`/`OPTIONS` loads — `safari.corbettgov.org` includes
        third-party checkout scripts and initial state fetches in its boot bundle and stays
        stuck on `Loading...` if passive page assets are aborted. Top-level navigation to
        checkout/payment routes is still blocked across all methods.
        """
        upper_method = (method or "GET").upper()
        res_type = (resource_type or "").lower()
        parsed = urlparse(url or "")
        host = (parsed.hostname or "").lower()
        path = (parsed.path or "").lower()

        # Never abort passive static subresources (JS bundles, CSS, fonts, images)
        if res_type in {"script", "stylesheet", "image", "font", "media", "manifest"}:
            return False

        is_payment_host = any(host == gw or host.endswith(f".{gw}") for gw in _PAYMENT_GATEWAY_HOSTS)

        # Block any top-level page navigation or payment API mutation to payment gateways
        if is_payment_host:
            if upper_method in {"POST", "PUT", "PATCH", "DELETE"}:
                return True
            if any(seg in path for seg in ("/checkout", "/orders", "/payments", "/pay")):
                # Allow passive checkout.js script even when resource_type wasn't passed
                if path.endswith(".js") or path.endswith(".css"):
                    return False
                return True
            return False

        # Block top-level document navigation into booking/checkout/payment pages
        if res_type == "document":
            for forbidden in FORBIDDEN_URL_SEGMENTS:
                if path == forbidden or path.startswith(f"{forbidden}/"):
                    return True
            return False

        # On write verbs (POST/PUT/PATCH/DELETE), block any order/cart/hold/OTP/payment call
        if upper_method in {"POST", "PUT", "PATCH", "DELETE"}:
            for pattern in _MUTATING_BOOKING_PATH_PATTERNS:
                if pattern.search(path):
                    return True

        return False

"""
E2E tests for waitlist API against the live dev environment.

Tests hit the deployed API Gateway and DynamoDB table directly.
No mocking — these verify real infrastructure behavior.

Run:
    cd chat-api/backend
    python -m pytest tests/e2e/test_waitlist_e2e.py -v -m e2e

Requirements:
    - AWS credentials configured (for DynamoDB cleanup)
    - Dev environment deployed with waitlist routes enabled
"""

import os
import re
import uuid

import boto3
import pytest
import requests

pytestmark = [pytest.mark.e2e, pytest.mark.slow]

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE_URL = os.environ.get(
    "WAITLIST_API_BASE_URL",
    "https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev",
)
WAITLIST_TABLE = os.environ.get("WAITLIST_TABLE", "waitlist-dev-buffett")
REQUEST_TIMEOUT = 15  # seconds


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dynamodb_table():
    """Get a reference to the live waitlist DynamoDB table for cleanup."""
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    return dynamodb.Table(WAITLIST_TABLE)


@pytest.fixture(scope="module")
def test_emails():
    """Generate unique test emails for this run and track them for cleanup."""
    run_id = uuid.uuid4().hex[:6]
    emails = {
        "user_a": f"e2e-a-{run_id}@testbuffett.com",
        "user_b": f"e2e-b-{run_id}@testbuffett.com",
        "user_c": f"e2e-c-{run_id}@testbuffett.com",
    }
    return emails


@pytest.fixture(scope="module")
def signup_user_a(test_emails, cleanup_entries):
    """Sign up user A and return the response data. Registers for cleanup."""
    resp = requests.post(
        f"{API_BASE_URL}/waitlist/signup",
        json={"email": test_emails["user_a"]},
        timeout=REQUEST_TIMEOUT,
    )
    assert resp.status_code == 201, f"User A signup failed: {resp.text}"
    data = resp.json()
    cleanup_entries.append(test_emails["user_a"])
    return data


@pytest.fixture(scope="module")
def signup_user_b(test_emails, signup_user_a, cleanup_entries):
    """Sign up user B with user A's referral code. Registers for cleanup."""
    resp = requests.post(
        f"{API_BASE_URL}/waitlist/signup",
        json={
            "email": test_emails["user_b"],
            "referral_code": signup_user_a["referral_code"],
        },
        timeout=REQUEST_TIMEOUT,
    )
    assert resp.status_code == 201, f"User B signup failed: {resp.text}"
    data = resp.json()
    cleanup_entries.append(test_emails["user_b"])
    return data


@pytest.fixture(scope="module")
def cleanup_entries(dynamodb_table):
    """Track emails to delete from DynamoDB after the test module completes."""
    entries = []
    yield entries
    # Cleanup: delete all test entries
    for email in entries:
        try:
            dynamodb_table.delete_item(Key={"email": email})
        except Exception:
            pass
    # Also clean up any rate-limit entries our IP may have created
    # (these will TTL out in 1 hour, but clean up proactively)


# ---------------------------------------------------------------------------
# AC-1: Signup happy path
# ---------------------------------------------------------------------------

class TestSignupHappyPath:
    """AC-1: POST /waitlist/signup returns 201 with expected fields."""

    def test_signup_returns_201(self, signup_user_a, test_emails):
        assert signup_user_a["email"] == test_emails["user_a"]
        assert signup_user_a["status"] == "waitlisted"
        assert signup_user_a["referral_count"] == 0
        assert signup_user_a["message"] == "You're on the waitlist!"

    def test_signup_returns_referral_code(self, signup_user_a):
        code = signup_user_a["referral_code"]
        assert re.match(r"^BUFF-[A-Z0-9]{4,6}$", code), f"Bad referral code format: {code}"

    def test_signup_returns_position(self, signup_user_a):
        assert isinstance(signup_user_a["position"], int)
        assert signup_user_a["position"] >= 1

    def test_signup_returns_tiers(self, signup_user_a):
        tiers = signup_user_a["tiers"]
        assert len(tiers) == 3
        assert tiers[0]["name"] == "Early Access"
        assert tiers[0]["threshold"] == 1
        assert tiers[1]["threshold"] == 3
        assert tiers[2]["threshold"] == 10

    def test_signup_returns_referral_link(self, signup_user_a):
        link = signup_user_a["referral_link"]
        code = signup_user_a["referral_code"]
        assert link.endswith(f"?ref={code}")


# ---------------------------------------------------------------------------
# AC-3: Duplicate signup returns 409
# ---------------------------------------------------------------------------

class TestDuplicateSignup:
    """AC-3: Re-signup with same email returns 409 with existing code."""

    def test_duplicate_returns_409(self, signup_user_a, test_emails):
        resp = requests.post(
            f"{API_BASE_URL}/waitlist/signup",
            json={"email": test_emails["user_a"]},
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "Email already registered"
        assert data["referral_code"] == signup_user_a["referral_code"]


# ---------------------------------------------------------------------------
# AC-4: Referral chain
# ---------------------------------------------------------------------------

class TestReferralChain:
    """AC-4: User B signs up with User A's code -> User A gets credit."""

    def test_referral_credits_referrer(self, signup_user_a, signup_user_b, test_emails):
        """After user B signs up with A's code, A's referral_count should be >= 1."""
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/status",
            params={
                "email": test_emails["user_a"],
                "code": signup_user_a["referral_code"],
            },
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["referral_count"] >= 1, (
            f"Expected referral_count >= 1, got {data['referral_count']}"
        )

    def test_referrer_promoted_to_early_access(self, signup_user_a, signup_user_b, test_emails):
        """User A should be promoted to early_access after 1 referral."""
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/status",
            params={
                "email": test_emails["user_a"],
                "code": signup_user_a["referral_code"],
            },
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "early_access", (
            f"Expected early_access, got {data['status']}"
        )

    def test_referrer_has_current_tier(self, signup_user_a, signup_user_b, test_emails):
        """User A with 1 referral should have Early Access as current tier."""
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/status",
            params={
                "email": test_emails["user_a"],
                "code": signup_user_a["referral_code"],
            },
            timeout=REQUEST_TIMEOUT,
        )
        data = resp.json()
        assert data["current_tier"] is not None
        assert data["current_tier"]["name"] == "Early Access"

    def test_referred_user_has_no_credit(self, signup_user_b, test_emails):
        """User B (the referred user) should have 0 referrals themselves."""
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/status",
            params={
                "email": test_emails["user_b"],
                "code": signup_user_b["referral_code"],
            },
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["referral_count"] == 0


# ---------------------------------------------------------------------------
# AC-2: Status endpoint happy path
# ---------------------------------------------------------------------------

class TestStatusEndpoint:
    """AC-2: GET /waitlist/status returns dashboard data."""

    def test_status_returns_position(self, signup_user_a, test_emails):
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/status",
            params={
                "email": test_emails["user_a"],
                "code": signup_user_a["referral_code"],
            },
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["position"], int)
        assert data["position"] >= 1

    def test_status_returns_tier_progress(self, signup_user_a, test_emails):
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/status",
            params={
                "email": test_emails["user_a"],
                "code": signup_user_a["referral_code"],
            },
            timeout=REQUEST_TIMEOUT,
        )
        data = resp.json()
        assert "current_tier" in data
        assert "next_tier" in data
        assert "tiers" in data
        assert "referral_link" in data

    def test_status_returns_referral_link(self, signup_user_a, test_emails):
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/status",
            params={
                "email": test_emails["user_a"],
                "code": signup_user_a["referral_code"],
            },
            timeout=REQUEST_TIMEOUT,
        )
        data = resp.json()
        assert data["referral_code"] == signup_user_a["referral_code"]
        assert signup_user_a["referral_code"] in data["referral_link"]


# ---------------------------------------------------------------------------
# AC-5: Validation errors
# ---------------------------------------------------------------------------

class TestValidationErrors:
    """AC-5: Invalid inputs return 400."""

    def test_missing_email_returns_400(self):
        resp = requests.post(
            f"{API_BASE_URL}/waitlist/signup",
            json={},
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 400
        assert "required" in resp.json()["error"].lower()

    def test_invalid_email_format_returns_400(self):
        resp = requests.post(
            f"{API_BASE_URL}/waitlist/signup",
            json={"email": "not-an-email"},
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 400
        assert "format" in resp.json()["error"].lower()

    def test_disposable_email_returns_400(self):
        resp = requests.post(
            f"{API_BASE_URL}/waitlist/signup",
            json={"email": f"test-{uuid.uuid4().hex[:6]}@mailinator.com"},
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 400
        assert "disposable" in resp.json()["error"].lower()

    def test_invalid_json_returns_400(self):
        resp = requests.post(
            f"{API_BASE_URL}/waitlist/signup",
            data="not json at all",
            headers={"Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# AC-6: Status with unknown email returns 404
# ---------------------------------------------------------------------------

class TestStatusNotFound:
    """AC-6: Email not on waitlist returns 404."""

    def test_unknown_email_returns_404(self):
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/status",
            params={
                "email": f"nonexistent-{uuid.uuid4().hex[:8]}@testbuffett.com",
                "code": "BUFF-ZZZZ",
            },
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["error"].lower()


# ---------------------------------------------------------------------------
# AC-7: Status with wrong code returns 403
# ---------------------------------------------------------------------------

class TestStatusForbidden:
    """AC-7: Mismatched email+code returns 403."""

    def test_wrong_code_returns_403(self, signup_user_a, test_emails):
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/status",
            params={
                "email": test_emails["user_a"],
                "code": "BUFF-WRONG",
            },
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 403
        assert "invalid" in resp.json()["error"].lower()

    def test_missing_params_returns_400(self):
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/status",
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 400
        assert "required" in resp.json()["error"].lower()


# ---------------------------------------------------------------------------
# AC-8: CORS preflight
# ---------------------------------------------------------------------------

class TestCORSPreflight:
    """AC-8: OPTIONS requests return CORS headers."""

    def test_signup_options_returns_200(self):
        resp = requests.options(
            f"{API_BASE_URL}/waitlist/signup",
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 200

    def test_status_options_returns_200(self):
        resp = requests.options(
            f"{API_BASE_URL}/waitlist/status",
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 200

    def test_options_returns_cors_body(self):
        resp = requests.options(
            f"{API_BASE_URL}/waitlist/signup",
            timeout=REQUEST_TIMEOUT,
        )
        data = resp.json()
        assert data["message"] == "CORS preflight OK"


# ---------------------------------------------------------------------------
# Edge case: Invalid referral code silently ignored
# ---------------------------------------------------------------------------

class TestInvalidReferralCode:
    """Signup with invalid referral code still succeeds (code is ignored)."""

    def test_invalid_referral_code_ignored(self, test_emails, cleanup_entries):
        resp = requests.post(
            f"{API_BASE_URL}/waitlist/signup",
            json={
                "email": test_emails["user_c"],
                "referral_code": "BUFF-NOPE",
            },
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 201
        cleanup_entries.append(test_emails["user_c"])
        data = resp.json()
        assert data["email"] == test_emails["user_c"]
        assert data["status"] == "waitlisted"

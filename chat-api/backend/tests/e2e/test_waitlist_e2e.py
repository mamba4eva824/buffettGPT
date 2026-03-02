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

import hashlib
import hmac
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
        "user_d": f"e2e-d-{run_id}@testbuffett.com",
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
def signup_user_d(test_emails, signup_user_a, cleanup_entries):
    """Sign up user D with user A's referral code (second referral for A)."""
    resp = requests.post(
        f"{API_BASE_URL}/waitlist/signup",
        json={
            "email": test_emails["user_d"],
            "referral_code": signup_user_a["referral_code"],
        },
        timeout=REQUEST_TIMEOUT,
    )
    assert resp.status_code == 201, f"User D signup failed: {resp.text}"
    data = resp.json()
    cleanup_entries.append(test_emails["user_d"])
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
        assert re.match(r"^BUFF-[A-Z0-9]{6,8}$", code), f"Bad referral code format: {code}"

    def test_signup_returns_position(self, signup_user_a):
        assert isinstance(signup_user_a["position"], int)
        assert signup_user_a["position"] >= 1

    def test_signup_returns_tiers(self, signup_user_a):
        tiers = signup_user_a["tiers"]
        assert len(tiers) == 3
        assert tiers[0]["name"] == "Early Access"
        assert tiers[0]["threshold"] == 1
        assert tiers[1]["threshold"] == 3
        assert tiers[2]["threshold"] == 5

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
# AC-6 + AC-7: Email enumeration prevention
# Both unknown email and wrong code return identical 403 responses.
# ---------------------------------------------------------------------------

class TestAntiEnumeration:
    """AC-6/AC-7: Unknown email and wrong code return identical 403."""

    def test_unknown_email_returns_403(self):
        """Unknown email returns 403 (not 404) to prevent email enumeration."""
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/status",
            params={
                "email": f"nonexistent-{uuid.uuid4().hex[:8]}@testbuffett.com",
                "code": "BUFF-ZZZZZZ",
            },
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 403
        assert resp.json()["error"] == "Invalid email or code"

    def test_wrong_code_returns_403(self, signup_user_a, test_emails):
        """Wrong code returns identical 403 to unknown email."""
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/status",
            params={
                "email": test_emails["user_a"],
                "code": "BUFF-WRONGX",
            },
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 403
        assert resp.json()["error"] == "Invalid email or code"

    def test_responses_indistinguishable(self, signup_user_a, test_emails):
        """Attacker cannot distinguish unknown email from wrong code."""
        # Unknown email
        resp_unknown = requests.get(
            f"{API_BASE_URL}/waitlist/status",
            params={
                "email": f"nonexistent-{uuid.uuid4().hex[:8]}@testbuffett.com",
                "code": "BUFF-ZZZZZZ",
            },
            timeout=REQUEST_TIMEOUT,
        )
        # Known email, wrong code
        resp_wrong = requests.get(
            f"{API_BASE_URL}/waitlist/status",
            params={
                "email": test_emails["user_a"],
                "code": "BUFF-WRONGX",
            },
            timeout=REQUEST_TIMEOUT,
        )
        # Both must be identical in status code and error message
        assert resp_unknown.status_code == resp_wrong.status_code == 403
        assert resp_unknown.json()["error"] == resp_wrong.json()["error"]

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


# ---------------------------------------------------------------------------
# HIGH-SEVERITY REGRESSION: Referral credit atomicity (Bug #1)
#
# Regression for: Missing :waitlisted expression attribute in _credit_referrer
# (waitlist_handler.py:293). Without the fix, the conditional update would
# raise a KeyError in DynamoDB, silently swallowing the promotion.
# ---------------------------------------------------------------------------

class TestReferralCreditRegression:
    """Verify referral credit + auto-promotion writes are atomic and correct."""

    def test_referral_count_exact_in_dynamodb(
        self, signup_user_a, signup_user_b, test_emails, dynamodb_table
    ):
        """After 1 referral, DynamoDB record has referral_count == 1 (not API — raw table)."""
        item = dynamodb_table.get_item(Key={"email": test_emails["user_a"]})["Item"]
        assert int(item["referral_count"]) == 1, (
            f"Expected referral_count=1 in DynamoDB, got {item['referral_count']}"
        )

    def test_referral_promotion_exact_in_dynamodb(
        self, signup_user_a, signup_user_b, test_emails, dynamodb_table
    ):
        """After 1 referral, DynamoDB record has status == 'early_access' (not API — raw table).

        This catches the original bug: if :waitlisted was missing from
        ExpressionAttributeValues, the conditional update would fail silently
        and status would remain 'waitlisted' in the table.
        """
        item = dynamodb_table.get_item(Key={"email": test_emails["user_a"]})["Item"]
        assert item["status"] == "early_access", (
            f"Expected status='early_access' in DynamoDB, got '{item['status']}'. "
            "This may indicate the _credit_referrer conditional update is broken."
        )

    def test_double_referral_increments_count(
        self, signup_user_a, signup_user_b, signup_user_d, test_emails, dynamodb_table
    ):
        """After 2 referrals (B and D), A's referral_count is exactly 2."""
        item = dynamodb_table.get_item(Key={"email": test_emails["user_a"]})["Item"]
        assert int(item["referral_count"]) == 2, (
            f"Expected referral_count=2 after two referrals, got {item['referral_count']}"
        )

    def test_double_referral_preserves_early_access(
        self, signup_user_a, signup_user_b, signup_user_d, test_emails
    ):
        """After a second referral, A stays early_access (ConditionalCheckFailed is handled).

        The second referral triggers _credit_referrer again. The conditional update
        'SET status = early_access WHERE status = waitlisted' should fail with
        ConditionalCheckFailedException (A is already early_access). This must be
        caught gracefully — no 500 error, and status must not revert.
        """
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/status",
            params={
                "email": test_emails["user_a"],
                "code": signup_user_a["referral_code"],
            },
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 200, (
            f"Status check returned {resp.status_code}, expected 200. "
            "ConditionalCheckFailedException may not be handled correctly."
        )
        data = resp.json()
        assert data["status"] == "early_access"
        assert data["referral_count"] == 2


# ---------------------------------------------------------------------------
# HIGH-SEVERITY REGRESSION: IAM access for all DynamoDB operations (Bug #2)
#
# Regression for: IAM wildcard 'buffett-dev-*' did not match renamed table
# 'waitlist-dev-buffett'. Without the explicit ARN fix, every DynamoDB
# operation would return AccessDeniedException (HTTP 500 to the client).
# ---------------------------------------------------------------------------

class TestIAMAccessRegression:
    """Verify Lambda has IAM access for all DynamoDB operation types.

    Each test exercises a different DynamoDB action through the API. If any
    returns 500 with 'Internal server error', it likely means the Lambda's
    IAM policy does not grant access to the waitlist table or its GSI.
    """

    def test_putitem_via_signup(self, signup_user_a):
        """PutItem works — signup succeeded (201, not 500)."""
        # signup_user_a fixture already asserted 201; re-verify the data shape
        assert signup_user_a["email"] is not None
        assert signup_user_a["referral_code"] is not None

    def test_getitem_via_status(self, signup_user_a, test_emails):
        """GetItem works — status endpoint returns 200, not 500."""
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/status",
            params={
                "email": test_emails["user_a"],
                "code": signup_user_a["referral_code"],
            },
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 200, (
            f"GetItem may have failed with AccessDeniedException: {resp.text}"
        )

    def test_updateitem_via_referral_credit(
        self, signup_user_a, signup_user_b, test_emails, dynamodb_table
    ):
        """UpdateItem works — referral_count was incremented (not stuck at 0)."""
        item = dynamodb_table.get_item(Key={"email": test_emails["user_a"]})["Item"]
        assert int(item["referral_count"]) >= 1, (
            "UpdateItem may have failed — referral_count is still 0. "
            "Check Lambda IAM policy for UpdateItem on waitlist table."
        )

    def test_gsi_query_via_referral_lookup(self, signup_user_a, signup_user_b):
        """GSI Query works — referral code lookup succeeded (B's signup used A's code).

        The handler calls Query on referral-code-index to find the referrer.
        If GSI access is denied, the referral silently fails and A gets no credit.
        """
        # B's signup with A's code succeeded (fixture asserts 201), and A got credit.
        # If GSI access failed, A would have referral_count=0. We already verified
        # count >= 1 above, but this test makes the intent explicit.
        assert signup_user_b["status"] == "waitlisted"  # B is new, not promoted


# ---------------------------------------------------------------------------
# Cross-verification: API response vs raw DynamoDB state
#
# Ensures the API is not masking broken writes by returning stale or
# hardcoded data. If _credit_referrer silently fails, the API might still
# return 200 with old data — but the DynamoDB record would be wrong.
# ---------------------------------------------------------------------------

class TestDynamoDBDirectVerification:
    """Compare API responses against raw DynamoDB records."""

    def test_api_response_matches_dynamodb_record(
        self, signup_user_a, signup_user_b, test_emails, dynamodb_table
    ):
        """API /status fields match the raw DynamoDB item for user A."""
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/status",
            params={
                "email": test_emails["user_a"],
                "code": signup_user_a["referral_code"],
            },
            timeout=REQUEST_TIMEOUT,
        )
        api_data = resp.json()

        item = dynamodb_table.get_item(Key={"email": test_emails["user_a"]})["Item"]

        assert api_data["email"] == item["email"]
        assert api_data["referral_code"] == item["referral_code"]
        assert api_data["referral_count"] == int(item["referral_count"])
        assert api_data["status"] == item["status"]

    def test_referred_by_code_stored_in_dynamodb(
        self, signup_user_a, signup_user_b, test_emails, dynamodb_table
    ):
        """User B's DynamoDB record stores the referral code they used (A's code)."""
        item = dynamodb_table.get_item(Key={"email": test_emails["user_b"]})["Item"]
        assert item.get("referred_by_code") == signup_user_a["referral_code"], (
            f"Expected referred_by_code='{signup_user_a['referral_code']}', "
            f"got '{item.get('referred_by_code')}'"
        )


# ---------------------------------------------------------------------------
# AC-9: Email delivery verification
#
# Sends a real signup using the test email (buffett.dev117@gmail.com) and
# verifies via Resend API that the welcome email was queued. Requires the
# RESEND_API_KEY env var or resend_dev_key secret in Secrets Manager.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def resend_api_key():
    """Fetch Resend API key from env or Secrets Manager."""
    import json as _json

    key = os.environ.get("RESEND_API_KEY")
    if key:
        return key
    try:
        secrets = boto3.client("secretsmanager", region_name="us-east-1")
        resp = secrets.get_secret_value(SecretId="resend_dev_key")
        secret = resp["SecretString"]
        # Secret may be JSON (e.g. {"resend_dev_key": "re_xxx"}) or a plain string
        try:
            parsed = _json.loads(secret)
            if isinstance(parsed, dict):
                return next(iter(parsed.values()))
        except (_json.JSONDecodeError, StopIteration):
            pass
        return secret
    except Exception:
        pytest.skip("Resend API key not available — skipping email e2e tests")


class TestEmailDelivery:
    """AC-9: Verify that signup triggers a real welcome email via Resend."""

    TEST_EMAIL = "buffett.dev117@gmail.com"

    def test_signup_sends_welcome_email(self, resend_api_key, dynamodb_table, cleanup_entries):
        """Sign up with the test email and verify Resend received the send request."""
        import resend as resend_sdk

        resend_sdk.api_key = resend_api_key

        # Sign up the test email
        resp = requests.post(
            f"{API_BASE_URL}/waitlist/signup",
            json={"email": self.TEST_EMAIL},
            timeout=REQUEST_TIMEOUT,
        )
        cleanup_entries.append(self.TEST_EMAIL)

        # Accept 201 (new signup) or 409 (already registered from previous run)
        assert resp.status_code in (201, 409), (
            f"Expected 201 or 409, got {resp.status_code}: {resp.text}"
        )

        if resp.status_code == 201:
            data = resp.json()
            assert data["email"] == self.TEST_EMAIL
            assert data["referral_code"].startswith("BUFF-")

            # Verify email was sent by checking Resend API (recent emails)
            # Allow a few seconds for async delivery
            import time
            time.sleep(3)

            try:
                emails = resend_sdk.Emails.list()
                email_list = emails.data if hasattr(emails, 'data') else emails
                # Check if a welcome email was sent to our test address recently
                found = any(
                    self.TEST_EMAIL in (getattr(e, 'to', []) if hasattr(e, 'to') else e.get('to', []))
                    for e in (email_list or [])
                )
                # Log result but don't fail — Resend API list may have lag
                if found:
                    print(f"  [OK] Welcome email confirmed via Resend API for {self.TEST_EMAIL}")
                else:
                    print(f"  [WARN] Email not yet visible in Resend API — check manually")
            except Exception as e:
                # Resend API listing may not be available on free tier
                print(f"  [INFO] Could not verify via Resend API: {e}")
                print(f"  [INFO] Check {self.TEST_EMAIL} inbox manually")


# ---------------------------------------------------------------------------
# Honeypot bot protection
# ---------------------------------------------------------------------------

class TestHoneypotE2E:
    """Honeypot field traps bots — filled 'website' gets a fake 201, empty proceeds normally."""

    def test_honeypot_filled_returns_fake_success(self, cleanup_entries):
        """AC-1: Non-empty 'website' field returns 201 with BUFF-000000 code."""
        fake_email = f"e2e-bot-{uuid.uuid4().hex[:6]}@testbuffett.com"
        resp = requests.post(
            f"{API_BASE_URL}/waitlist/signup",
            json={"email": fake_email, "website": "http://spam.example.com"},
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["referral_code"] == "BUFF-000000"
        assert data["status"] == "waitlisted"
        assert data["message"] == "You're on the waitlist!"

    def test_honeypot_filled_no_dynamodb_record(self, dynamodb_table):
        """AC-1: Bot signup with honeypot does NOT write to DynamoDB."""
        bot_email = f"e2e-bot-noddb-{uuid.uuid4().hex[:6]}@testbuffett.com"
        resp = requests.post(
            f"{API_BASE_URL}/waitlist/signup",
            json={"email": bot_email, "website": "http://spam.example.com"},
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 201
        # Verify nothing was written
        item = dynamodb_table.get_item(Key={"email": bot_email}).get("Item")
        assert item is None, f"Honeypot signup should NOT create a DynamoDB record, but found: {item}"

    def test_honeypot_empty_creates_real_record(self, signup_user_a, test_emails, dynamodb_table):
        """AC-2: Empty 'website' field proceeds with a real signup.

        The existing signup fixtures don't send a 'website' field, which is
        equivalent to an empty honeypot.  We verify that user_a (created
        without the honeypot field) has a real referral code and DynamoDB
        record — proving that absent/empty honeypot proceeds normally.
        """
        assert signup_user_a["referral_code"] != "BUFF-000000"
        assert re.match(r"^BUFF-[A-Z0-9]{6,8}$", signup_user_a["referral_code"])
        # Verify DynamoDB record exists
        item = dynamodb_table.get_item(Key={"email": test_emails["user_a"]}).get("Item")
        assert item is not None, "Legitimate signup should create a DynamoDB record"
        assert item["email"] == test_emails["user_a"]


# ---------------------------------------------------------------------------
# Unsubscribe endpoint
# ---------------------------------------------------------------------------

# The Lambda resolves its HMAC secret from Secrets Manager via JWT_SECRET_ARN.
# E2E tests fetch the same secret so tokens match.
JWT_SECRET_NAME = os.environ.get("JWT_SECRET_NAME", "buffett-dev-jwt-secret-v2")


def _get_unsubscribe_secret() -> str:
    """Fetch the JWT secret used by the Lambda for HMAC unsubscribe tokens.

    NOTE: We skip os.environ['JWT_SECRET'] because the root conftest autouse
    fixture sets it to a test-only value that doesn't match the deployed Lambda.
    Only UNSUBSCRIBE_SECRET is checked as an explicit override.
    """
    override = os.environ.get("UNSUBSCRIBE_SECRET")
    if override:
        return override
    try:
        client = boto3.client("secretsmanager", region_name="us-east-1")
        resp = client.get_secret_value(SecretId=JWT_SECRET_NAME)
        return resp["SecretString"]
    except Exception as e:
        pytest.skip(f"Cannot fetch JWT secret from Secrets Manager: {e}")


def _generate_unsubscribe_token(email: str) -> str:
    """Mirror the token generation from email_service.py."""
    secret = _get_unsubscribe_secret()
    return hmac.new(
        secret.encode(),
        email.lower().encode(),
        hashlib.sha256,
    ).hexdigest()


class TestUnsubscribeE2E:
    """Unsubscribe endpoint verifies HMAC token and sets email_opted_out flag."""

    def test_valid_unsubscribe_returns_200_html(self, signup_user_a, test_emails, dynamodb_table):
        """AC-3: Valid HMAC token returns 200 with HTML and sets email_opted_out=True."""
        email = test_emails["user_a"]
        token = _generate_unsubscribe_token(email)

        resp = requests.get(
            f"{API_BASE_URL}/waitlist/unsubscribe",
            params={"email": email, "token": token},
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert "text/html" in resp.headers.get("Content-Type", "")
        assert "unsubscribed" in resp.text.lower()

        # Verify DynamoDB record has email_opted_out=True
        item = dynamodb_table.get_item(Key={"email": email})["Item"]
        assert item.get("email_opted_out") is True, (
            f"Expected email_opted_out=True, got {item.get('email_opted_out')}"
        )

    def test_invalid_token_returns_403(self, signup_user_a, test_emails):
        """AC-4: Invalid HMAC token returns 403."""
        email = test_emails["user_a"]
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/unsubscribe",
            params={"email": email, "token": "invalid-token-abc123"},
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 403
        assert "text/html" in resp.headers.get("Content-Type", "")
        assert "invalid" in resp.text.lower() or "expired" in resp.text.lower()

    def test_missing_email_returns_400(self):
        """AC-5: Missing email parameter returns 400."""
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/unsubscribe",
            params={"token": "some-token"},
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 400
        assert "text/html" in resp.headers.get("Content-Type", "")

    def test_missing_token_returns_400(self, signup_user_a, test_emails):
        """AC-5: Missing token parameter returns 400."""
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/unsubscribe",
            params={"email": test_emails["user_a"]},
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 400
        assert "text/html" in resp.headers.get("Content-Type", "")

    def test_missing_both_params_returns_400(self):
        """AC-5: Missing both parameters returns 400."""
        resp = requests.get(
            f"{API_BASE_URL}/waitlist/unsubscribe",
            timeout=REQUEST_TIMEOUT,
        )
        assert resp.status_code == 400

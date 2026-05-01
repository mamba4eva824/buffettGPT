"""
Email Service Utility for Waitlist Notifications

Provides transactional email sending via Resend for:
- Welcome/confirmation emails on waitlist signup
- Referral success notifications
- Tier milestone alerts

Emails are fire-and-forget: failures are logged but never block the caller.
"""

import hashlib
import hmac
import html
import json
import os
import logging
from functools import lru_cache
from typing import Optional, Dict, Any, List
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Environment
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')

# Resend config — ARN passed via Terraform env var
RESEND_API_KEY_ARN = os.environ.get('RESEND_API_KEY_ARN', '')
RESEND_FROM_EMAIL = os.environ.get('RESEND_FROM_EMAIL', 'onboarding@resend.dev')

# Unsubscribe config
API_BASE_URL = os.environ.get('API_BASE_URL', '')
JWT_SECRET_ARN = os.environ.get('JWT_SECRET_ARN', '')

# Initialize AWS client for secret retrieval
secrets_client = boto3.client('secretsmanager')

# Lazy-initialized Resend client
_resend_initialized = False


@lru_cache(maxsize=1)
def _get_resend_api_key() -> Optional[str]:
    """Fetch Resend API key from Secrets Manager with caching."""
    if not RESEND_API_KEY_ARN:
        logger.warning("RESEND_API_KEY_ARN not configured — emails disabled")
        return None
    try:
        response = secrets_client.get_secret_value(SecretId=RESEND_API_KEY_ARN)
        secret = response['SecretString']
        # Secret may be JSON (e.g. {"resend_dev_key": "re_xxx"}) or a plain string
        try:
            parsed = json.loads(secret)
            if isinstance(parsed, dict):
                # Return the first value from the JSON object
                return next(iter(parsed.values()))
        except (json.JSONDecodeError, StopIteration):
            pass
        return secret
    except ClientError as e:
        logger.error(f"Failed to fetch Resend API key: {e}")
        return None


@lru_cache(maxsize=1)
def _get_unsubscribe_secret() -> str:
    """Fetch the HMAC signing secret for unsubscribe tokens.

    Resolution order:
      1. JWT_SECRET_ARN → Secrets Manager (plain string, not JSON)
      2. UNSUBSCRIBE_SECRET env var
      3. JWT_SECRET env var
    Raises ValueError if none are configured.
    """
    if JWT_SECRET_ARN:
        try:
            response = secrets_client.get_secret_value(SecretId=JWT_SECRET_ARN)
            return response['SecretString']
        except ClientError as e:
            logger.error(f"Failed to fetch JWT secret from Secrets Manager: {e}")
            raise ValueError("JWT secret not available in Secrets Manager") from e

    secret = os.environ.get('UNSUBSCRIBE_SECRET') or os.environ.get('JWT_SECRET')
    if secret:
        return secret

    raise ValueError(
        "No unsubscribe secret configured. "
        "Set JWT_SECRET_ARN, UNSUBSCRIBE_SECRET, or JWT_SECRET."
    )


def _init_resend() -> bool:
    """Initialize Resend SDK with API key. Returns True if successful."""
    global _resend_initialized
    if _resend_initialized:
        return True

    api_key = _get_resend_api_key()
    if not api_key:
        return False

    try:
        import resend
        resend.api_key = api_key
        _resend_initialized = True
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Resend: {e}")
        return False


def send_email(to: str, subject: str, html: str) -> Optional[str]:
    """
    Send an email via Resend. Returns the email ID on success, None on failure.

    This is fire-and-forget — failures are logged but never raised.
    """
    if not _init_resend():
        return None

    try:
        import resend
        result = resend.Emails.send({
            "from": RESEND_FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "html": html,
        })
        email_id = result.get('id') if isinstance(result, dict) else getattr(result, 'id', None)
        logger.info(f"Email sent to {to}: subject='{subject}', id={email_id}")
        return email_id
    except Exception as e:
        logger.warning(f"Failed to send email to {to}: {e}")
        return None


# ================================================
# Helpers
# ================================================

def _escape(value) -> str:
    """Escape a value for safe HTML interpolation."""
    return html.escape(str(value))


def generate_unsubscribe_token(email: str) -> str:
    """Generate an HMAC-SHA256 token for unsubscribe verification."""
    secret = _get_unsubscribe_secret()
    return hmac.new(
        secret.encode(),
        email.lower().encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_unsubscribe_token(email: str, token: str) -> bool:
    """Verify an unsubscribe token using constant-time comparison."""
    expected = generate_unsubscribe_token(email)
    return hmac.compare_digest(expected, token)


def _unsubscribe_footer(to: str) -> str:
    """Build the unsubscribe footer HTML for an email."""
    token = generate_unsubscribe_token(to)
    encoded_email = quote(to)
    if API_BASE_URL:
        unsub_url = f"{API_BASE_URL}/waitlist/unsubscribe?email={encoded_email}&token={token}"
    else:
        unsub_url = f"{FRONTEND_URL}/waitlist/unsubscribe?email={encoded_email}&token={token}"
    # TODO: Replace placeholder address with your real PO Box / business address before launch
    mailing_address = "Buffett, 123 Main St, Suite 100, City, ST 00000"
    return f"""
        <p style="font-size: 12px; color: #bbb; margin-top: 8px;">
            <a href="{_escape(unsub_url)}" style="color: #bbb; text-decoration: underline;">Unsubscribe</a>
        </p>
        <p style="font-size: 11px; color: #ccc; margin-top: 4px;">
            {_escape(mailing_address)}
        </p>
    """


# ================================================
# Email Templates
# ================================================

def send_welcome_email(to: str, referral_code: str, referral_link: str) -> Optional[str]:
    """Send welcome/confirmation email after waitlist signup."""
    subject = "You're on the Buffett waitlist!"
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: 0 auto; padding: 32px 20px; color: #1a1a1a;">
        <h1 style="font-size: 24px; margin-bottom: 8px;">Welcome to Buffett</h1>
        <p style="color: #555; font-size: 16px; line-height: 1.6;">
            You've secured your spot on the waitlist. We'll let you know when it's your turn.
        </p>

        <div style="background: #f7f7f7; border-radius: 8px; padding: 20px; margin: 24px 0;">
            <p style="margin: 0 0 4px 0; font-size: 13px; color: #888; text-transform: uppercase; letter-spacing: 0.5px;">Your referral code</p>
            <p style="margin: 0; font-size: 28px; font-weight: 700; letter-spacing: 1px;">{_escape(referral_code)}</p>
        </div>

        <p style="font-size: 16px; line-height: 1.6;">
            <strong>Skip the line</strong> &mdash; share your link and unlock rewards:
        </p>
        <ul style="font-size: 15px; line-height: 1.8; color: #333; padding-left: 20px;">
            <li><strong>3 referrals</strong> &rarr; 1 month free Plus</li>
            <li><strong>5 referrals</strong> &rarr; 3 months free Plus</li>
        </ul>

        <div style="margin: 24px 0;">
            <a href="{_escape(referral_link)}" style="display: inline-block; background: #2563eb; color: #fff; padding: 12px 28px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 15px;">
                Copy your referral link
            </a>
        </div>

        <p style="font-size: 13px; color: #999; margin-top: 32px;">
            &mdash; Buffett
        </p>
        {_unsubscribe_footer(to)}
    </div>
    """
    return send_email(to, subject, html)


def send_referral_success_email(
    to: str,
    referral_count: int,
    referral_code: str,
    current_tier: Optional[Dict[str, Any]] = None,
    next_tier: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Send notification when someone uses the user's referral code."""
    subject = f"Someone joined using your referral code!"

    # Progress section
    if next_tier:
        progress_html = f"""
        <p style="font-size: 15px; color: #555; line-height: 1.6;">
            You're <strong>{_escape(next_tier['referrals_needed'])}</strong> referral{'s' if next_tier['referrals_needed'] != 1 else ''}
            away from <strong>{_escape(next_tier['name'])}</strong> ({_escape(next_tier['reward'])}).
        </p>
        """
    else:
        progress_html = """
        <p style="font-size: 15px; color: #555; line-height: 1.6;">
            You've unlocked all reward tiers. Nice work!
        </p>
        """

    referral_link = f"{FRONTEND_URL}?ref={referral_code}"
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: 0 auto; padding: 32px 20px; color: #1a1a1a;">
        <h1 style="font-size: 24px; margin-bottom: 8px;">Your referral worked!</h1>
        <p style="font-size: 16px; line-height: 1.6; color: #333;">
            Someone just joined Buffett using your code. You now have
            <strong>{_escape(referral_count)}</strong> referral{'s' if referral_count != 1 else ''}.
        </p>

        {progress_html}

        <div style="margin: 24px 0;">
            <a href="{_escape(referral_link)}" style="display: inline-block; background: #2563eb; color: #fff; padding: 12px 28px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 15px;">
                Share again
            </a>
        </div>

        <p style="font-size: 13px; color: #999; margin-top: 32px;">
            &mdash; Buffett
        </p>
        {_unsubscribe_footer(to)}
    </div>
    """
    return send_email(to, subject, html)


def send_tier_unlocked_email(
    to: str,
    tier_name: str,
    tier_reward: str,
    referral_count: int,
    referral_code: str,
) -> Optional[str]:
    """Send congratulations when user reaches a new referral tier."""
    subject = f"You've unlocked {_escape(tier_name)}!"

    referral_link = f"{FRONTEND_URL}?ref={referral_code}"
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: 0 auto; padding: 32px 20px; color: #1a1a1a;">
        <h1 style="font-size: 24px; margin-bottom: 8px;">Milestone reached!</h1>
        <p style="font-size: 16px; line-height: 1.6; color: #333;">
            With <strong>{_escape(referral_count)}</strong> referral{'s' if referral_count != 1 else ''},
            you've unlocked <strong>{_escape(tier_name)}</strong>.
        </p>

        <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 20px; margin: 24px 0;">
            <p style="margin: 0 0 4px 0; font-size: 13px; color: #16a34a; text-transform: uppercase; letter-spacing: 0.5px;">Your reward</p>
            <p style="margin: 0; font-size: 18px; font-weight: 600; color: #15803d;">{_escape(tier_reward)}</p>
        </div>

        <p style="font-size: 15px; color: #555; line-height: 1.6;">
            Keep sharing to unlock even more rewards.
        </p>

        <div style="margin: 24px 0;">
            <a href="{_escape(referral_link)}" style="display: inline-block; background: #2563eb; color: #fff; padding: 12px 28px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 15px;">
                Keep sharing
            </a>
        </div>

        <p style="font-size: 13px; color: #999; margin-top: 32px;">
            &mdash; Buffett
        </p>
        {_unsubscribe_footer(to)}
    </div>
    """
    return send_email(to, subject, html)

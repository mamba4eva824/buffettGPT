"""
Security tests: verify no real secrets are committed in tracked documentation.

Run with: pytest tests/security/test_secret_scanning.py -v
"""

import os
import re

# Repo root (four levels up from this file)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
DOCS_DIR = os.path.join(REPO_ROOT, 'docs')


def _scan_files(directory, extension='.md'):
    """Yield (filepath, line_number, line) for all files with the given extension."""
    for root, _dirs, files in os.walk(directory):
        for fname in files:
            if fname.endswith(extension):
                fpath = os.path.join(root, fname)
                with open(fpath, 'r', errors='ignore') as f:
                    for lineno, line in enumerate(f, start=1):
                        yield fpath, lineno, line


class TestNoStripeSecretsInDocs:
    """Ensure no real Stripe secrets appear in tracked documentation."""

    # Patterns that indicate real (non-placeholder) secrets
    SECRET_PATTERNS = [
        # Webhook signing secrets: whsec_ followed by 20+ hex chars
        (r'whsec_[a-f0-9]{20,}', 'Stripe webhook secret'),
        # Live secret keys
        (r'sk_live_[A-Za-z0-9]{20,}', 'Stripe live secret key'),
        # Live restricted keys
        (r'rk_live_[A-Za-z0-9]{20,}', 'Stripe live restricted key'),
    ]

    def test_no_stripe_secrets_in_tracked_docs(self):
        """
        Given: All .md files under docs/
        When: Scanned for real Stripe secret patterns
        Then: No matches found (only placeholders like whsec_xxx are allowed)
        """
        violations = []
        for fpath, lineno, line in _scan_files(DOCS_DIR):
            for pattern, description in self.SECRET_PATTERNS:
                if re.search(pattern, line):
                    rel_path = os.path.relpath(fpath, REPO_ROOT)
                    violations.append(f"  {rel_path}:{lineno} — {description}")

        assert not violations, (
            f"Real Stripe secrets found in docs:\n" + "\n".join(violations)
        )

    def test_gitignore_covers_env_files(self):
        """
        Given: The root .gitignore
        When: Checked for .env coverage
        Then: Contains **/.env pattern to block env files at any depth
        """
        gitignore_path = os.path.join(REPO_ROOT, '.gitignore')
        assert os.path.exists(gitignore_path), ".gitignore not found at repo root"

        with open(gitignore_path) as f:
            content = f.read()

        assert '**/.env' in content, (
            ".gitignore missing '**/.env' pattern — env files could be committed"
        )

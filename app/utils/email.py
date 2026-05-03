"""
app/utils/email.py
───────────────────
Email utility helpers.
Pydantic's EmailStr already does RFC-5321 validation; this module
adds application-level checks (disposable domains, etc.).
"""

import re
from typing import Set

# A small static list of commonly abused disposable email domains.
# In production, replace with a third-party service or a larger dataset.
_DISPOSABLE_DOMAINS: Set[str] = {
    "mailinator.com",
    "guerrillamail.com",
    "10minutemail.com",
    "throwaway.email",
    "yopmail.com",
    "trashmail.com",
    "fakeinbox.com",
    "sharklasers.com",
    "guerrillamailblock.com",
    "dispostable.com",
}

_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)


def is_valid_email_format(email: str) -> bool:
    """Basic RFC-5321 regex check (Pydantic handles this, but useful standalone)."""
    return bool(_EMAIL_RE.match(email)) and len(email) <= 254


def is_disposable_email(email: str) -> bool:
    """Return True if the email's domain is on the known-disposable list."""
    try:
        domain = email.split("@")[1].lower()
        return domain in _DISPOSABLE_DOMAINS
    except IndexError:
        return False


def normalize_email(email: str) -> str:
    """Lowercase the entire email address for consistent storage."""
    return email.strip().lower()

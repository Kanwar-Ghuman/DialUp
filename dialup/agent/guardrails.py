"""Safety rules enforced in code, not just in the prompt.

The prompt asks the agent not to do these things. These checks make sure it can't.
Each check returns None if the action is allowed, or a short reason if it's blocked.
"""
import re

from playwright.async_api import Page

# Clicking something with this text commits the caller to something. Needs a "yes" first.
IRREVERSIBLE = re.compile(
    r"\b(book|hold|reserve|pay|purchase|buy|checkout|check out|place order|donate|subscribe)\b"
    r"|预订|预定|支付|付款|购买",
    re.IGNORECASE,
)
_SECRET_LABEL = re.compile(r"pass(word|code)|\bpin\b|密码", re.IGNORECASE)
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b")
_DIGIT_RUN = re.compile(r"(?:\d[ -]?){13,19}")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def looks_like_card_number(text: str) -> bool:
    for m in _DIGIT_RUN.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            return True
    return False


def check_value(label: str, value: str) -> str | None:
    """Text-only checks, no browser needed."""
    if _SECRET_LABEL.search(label):
        return "that is a password or PIN field. Never enter passwords. If a login is required, give_up."
    if looks_like_card_number(value):
        return "that looks like a card number. Never enter payment details. give_up instead."
    if _SSN.search(value):
        return "that looks like a Social Security or ID number. Never enter it."
    return None


async def check_fill(page: Page, label: str, value: str) -> str | None:
    reason = check_value(label, value)
    if reason:
        return reason
    try:
        kind = await page.get_by_label(label).first.get_attribute("type", timeout=2_000)
    except Exception:
        kind = None
    if (kind or "").lower() == "password":
        return "that is a password field. Never enter passwords. If a login is required, give_up."
    return None


def is_irreversible(click_text: str) -> bool:
    return bool(IRREVERSIBLE.search(click_text or ""))

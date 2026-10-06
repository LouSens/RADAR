"""The grounding check: a brief may only contain numbers that are in its payload.

Every number in the text is read back and looked for among the numbers in the payload.
One that is not there means the text says something the data does not, so the text is
rejected. This is what lets an optional language-model writer be used safely: whatever
it writes, an invented figure cannot reach the screen.
"""

import re
from typing import Any

from pydantic import BaseModel

# A number as written in prose: optional sign, digits with thousands separators, and
# an optional decimal part.
# The typographic minus sign, which formatted figures may use.
MINUS = "\u2212"
_NUMBER = re.compile(rf"(?<![\w.])[-+{MINUS}]?\d[\d,]*(?:\.\d+)?")
_TOLERANCE = 1e-9


def numbers_in_text(text: str) -> list[float]:
    """Every number written in the text, as a value. Signs and commas are understood."""
    found = []
    for match in _NUMBER.finditer(text):
        raw = match.group().replace(",", "").replace(MINUS, "-").lstrip("+")
        found.append(float(raw))
    return found


def _walk(value: Any) -> list[float]:
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, int | float):
        return [float(value)]
    if isinstance(value, str):
        return numbers_in_text(value)
    if isinstance(value, dict):
        return [n for item in value.values() for n in _walk(item)]
    if isinstance(value, list | tuple):
        return [n for item in value for n in _walk(item)]
    return []


def numbers_in_payload(payload: BaseModel | dict[str, Any]) -> list[float]:
    """Every number anywhere in the payload, including those inside its strings."""
    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    return _walk(data)


def ungrounded(text: str, payload: BaseModel | dict[str, Any]) -> list[float]:
    """The numbers in the text that are not in the payload. Empty means grounded.

    A number matches whatever its sign: "a loss of 3.4%" may come from -3.4.
    """
    allowed = {abs(n) for n in numbers_in_payload(payload)}
    return [
        n for n in numbers_in_text(text) if not any(abs(abs(n) - a) <= _TOLERANCE for a in allowed)
    ]


def check(text: str, payload: BaseModel | dict[str, Any]) -> bool:
    return not ungrounded(text, payload)

"""Wrap user text for a prompt so it cannot close or reopen the <data> tags."""

import re

_DATA_TAG = re.compile(r"<\s*(/?)\s*data\b", re.IGNORECASE)


def data(text) -> str:
    """Return `text` inside <data> tags, with any <data> or </data> it contains escaped.

    The system prompt tells the model to ignore instructions inside <data> tags. Escaping
    stops user text from ending the tag early and adding instructions outside it.
    """
    safe = _DATA_TAG.sub(lambda m: "&lt;" + m.group(1) + "data", str(text))
    return f"<data>{safe}</data>"

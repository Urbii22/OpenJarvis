from __future__ import annotations

import json
import re
from typing import Iterable

from openjarvis.core.types import ToolCall


_OPEN_APP_PATTERNS = (
    r"\babre\s+(.+)$",
    r"\babrir\s+(.+)$",
    r"\bopen\s+(.+)$",
    r"\blaunch\s+(.+)$",
)


def _clean_target(value: str) -> str:
    cleaned = value.strip().strip("?!. ")
    cleaned = re.sub(r"^(el|la|los|las)\s+", "", cleaned, flags=re.IGNORECASE)
    article_map = {
        "bloc de notas": "notepad",
        "explorador de archivos": "explorer",
    }
    lowered = cleaned.lower()
    return article_map.get(lowered, cleaned)


def infer_computer_use_tool(
    user_input: str,
    available_tools: Iterable[str],
) -> ToolCall | None:
    tools = set(available_tools)
    text = user_input.strip()
    lowered = text.lower()

    if "open_application" in tools:
        for pattern in _OPEN_APP_PATTERNS:
            match = re.search(pattern, lowered, flags=re.IGNORECASE)
            if not match:
                continue
            start, end = match.span(1)
            original_target = text[start:end]
            app = _clean_target(original_target)
            if app:
                return ToolCall(
                    id="fallback_open_application",
                    name="open_application",
                    arguments=json.dumps({"app": app}),
                )
    return None

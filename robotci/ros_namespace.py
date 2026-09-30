"""ROS namespace normalization without importing ROS into the Python core."""

from __future__ import annotations

import re

_NAMESPACE_RE = re.compile(r"(?:/[A-Za-z_][A-Za-z0-9_]*)+")


def normalize_ros_namespace(value: str) -> str:
    """Return an absolute namespace, using an empty string for the root graph."""
    if not isinstance(value, str):
        raise ValueError("ROS namespace must be a string")
    if value in {"", "/"}:
        return ""
    absolute = value if value.startswith("/") else f"/{value}"
    if _NAMESPACE_RE.fullmatch(absolute) is None:
        raise ValueError(
            "ROS namespace must contain slash-separated names starting with a letter or underscore"
        )
    return absolute

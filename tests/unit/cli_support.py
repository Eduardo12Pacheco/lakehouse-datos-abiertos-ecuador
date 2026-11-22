"""Shared helpers for asserting on CLI output in unit tests."""

from __future__ import annotations

import re

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def plain(text: str) -> str:
    """Return ``text`` without ANSI colour codes.

    GitHub Actions forces colour output, which splits option names such as
    ``--out`` with escape sequences. Strip them before substring assertions.
    """
    return _ANSI.sub("", text)

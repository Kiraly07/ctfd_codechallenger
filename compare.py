"""Output comparison.

Default mode is "trim":
  - CRLF and CR become LF
  - trailing whitespace on each line is removed
  - a single trailing newline is ignored
  - the remaining text must match exactly

"exact" compares the raw strings.
"whitespace-insensitive" collapses every run of whitespace to one space.
"""

from __future__ import annotations

from .constants import COMPARISON_MODES, DEFAULT_COMPARISON


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def trim_compare(actual: str, expected: str) -> bool:
    def _trim(value: str) -> str:
        value = normalize_newlines(value)
        lines = [line.rstrip() for line in value.split("\n")]
        # Drop one trailing empty line produced by a final newline.
        if lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)

    return _trim(actual) == _trim(expected)


def exact_compare(actual: str, expected: str) -> bool:
    return normalize_newlines(actual) == normalize_newlines(expected)


def whitespace_insensitive_compare(actual: str, expected: str) -> bool:
    def _collapse(value: str) -> str:
        return " ".join(normalize_newlines(value).split())

    return _collapse(actual) == _collapse(expected)


_MODES = {
    "trim": trim_compare,
    "exact": exact_compare,
    "whitespace-insensitive": whitespace_insensitive_compare,
}


def outputs_match(actual: str, expected: str, mode: str = DEFAULT_COMPARISON) -> bool:
    if mode not in COMPARISON_MODES:
        mode = DEFAULT_COMPARISON
    actual = actual or ""
    expected = expected or ""
    return _MODES[mode](actual, expected)

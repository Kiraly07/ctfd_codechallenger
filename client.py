"""HTTP client for a local Judge0 CE instance.

Source, stdin and the result fields travel base64-encoded. GCC writes
compile errors as raw bytes, and Judge0 CE 1.13.1 answers
"cannot be converted to UTF-8, use base64_encoded=true" when those bytes
are requested as text. Decoding here keeps that failure mode off the
player and off the comparison code.

wait=true is tried first. A still-queued submission, or a 400 that only
complains about wait, falls back to creating a submission and polling
the token.
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

import requests

from .constants import JUDGE0_TIMEOUT_SECONDS

log = logging.getLogger("ctfd.plugins.ctfd_code")

# Status ids from Judge0 CE /statuses.
STATUS_IN_QUEUE = 1
STATUS_PROCESSING = 2
STATUS_ACCEPTED = 3
STATUS_WRONG_ANSWER = 4
STATUS_TIME_LIMIT = 5
STATUS_COMPILATION = 6
STATUS_INTERNAL = 13

RUNTIME_STATUS_IDS = {7, 8, 9, 10, 11, 12, 14}

_TEXT_FIELDS = ("stdout", "stderr", "compile_output", "message")


class Judge0Error(Exception):
    """Judge0 could not be reached or returned an unusable response."""


def _headers(api_token: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_token:
        # Judge0 CE with AUTH_TOKEN set expects this header. Local installs
        # without auth leave the token empty and send nothing.
        headers["X-Auth-Token"] = api_token
    return headers


def _base(url: str) -> str:
    return (url or "").rstrip("/")


def _b64(text: str) -> str:
    return base64.b64encode((text or "").encode("utf-8")).decode("ascii")


def _unb64(value: Any) -> str:
    if not value or not isinstance(value, str):
        return ""
    try:
        return base64.b64decode(value).decode("utf-8", "replace")
    except (ValueError, TypeError):
        return ""


def _decode_body(body: dict) -> dict:
    """Turn a base64_encoded=true submission object into plain text fields."""
    if not isinstance(body, dict):
        return body
    for field in _TEXT_FIELDS:
        if body.get(field):
            body[field] = _unb64(body[field])
    return body


def submit(
    url: str,
    api_token: str,
    language_id: int,
    source_code: str,
    stdin: str,
    cpu_time_limit: float,
    memory_limit: int,
    expected_output: str | None = None,
) -> dict[str, Any]:
    """Run one program. Returns the Judge0 submission object.

    expected_output is optional. When it is sent, Judge0 itself marks the
    submission Wrong Answer. We still re-compare locally so comparison mode
    (trim / whitespace) is ours, not Judge0's exact match.
    """
    payload: dict[str, Any] = {
        "language_id": int(language_id),
        "source_code": _b64(source_code),
        "stdin": _b64(stdin if stdin is not None else ""),
        "cpu_time_limit": float(cpu_time_limit),
        "memory_limit": int(memory_limit),
    }
    # Intentionally not sending expected_output. Local comparison owns the
    # verdict so hidden expected text never has to match Judge0's rules.

    endpoint = _base(url) + "/submissions"
    params = {"base64_encoded": "true", "wait": "true"}
    try:
        response = requests.post(
            endpoint,
            params=params,
            json=payload,
            headers=_headers(api_token),
            timeout=JUDGE0_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise Judge0Error("Judge0 connection failed: {0}".format(exc.__class__.__name__)) from exc

    if response.status_code in (400, 422) and "wait" in response.text.lower():
        return _submit_and_poll(endpoint, api_token, payload)

    # 201 with an error field is how Judge0 CE reports "this result is not
    # valid UTF-8". The token is still valid; poll it back as base64.
    try:
        body = response.json()
    except ValueError as exc:
        raise Judge0Error("Judge0 returned a non-JSON response") from exc

    if response.status_code in (401, 403):
        raise Judge0Error("Judge0 rejected the request ({0})".format(response.status_code))

    if response.status_code >= 400 and not body.get("token"):
        raise Judge0Error("Judge0 returned HTTP {0}".format(response.status_code))

    body = _decode_body(body)
    status = (body.get("status") or {}).get("id")
    if body.get("token") and (
        status in (STATUS_IN_QUEUE, STATUS_PROCESSING, None) or body.get("error")
    ):
        return _poll(endpoint, api_token, body["token"])
    if response.status_code >= 400:
        raise Judge0Error("Judge0 returned HTTP {0}".format(response.status_code))
    return body


def _submit_and_poll(endpoint: str, api_token: str, payload: dict) -> dict:
    try:
        response = requests.post(
            endpoint,
            params={"base64_encoded": "true"},
            json=payload,
            headers=_headers(api_token),
            timeout=JUDGE0_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise Judge0Error("Judge0 connection failed: {0}".format(exc.__class__.__name__)) from exc

    if response.status_code in (401, 403):
        raise Judge0Error("Judge0 rejected the request ({0})".format(response.status_code))
    if response.status_code >= 400:
        raise Judge0Error("Judge0 returned HTTP {0}".format(response.status_code))

    try:
        body = response.json()
    except ValueError as exc:
        raise Judge0Error("Judge0 returned a non-JSON response") from exc

    token = body.get("token")
    if not token:
        raise Judge0Error("Judge0 did not return a submission token")
    return _poll(endpoint, api_token, token)


def _poll(endpoint: str, api_token: str, token: str) -> dict:
    deadline = time.monotonic() + JUDGE0_TIMEOUT_SECONDS
    last = {}
    while time.monotonic() < deadline:
        try:
            response = requests.get(
                "{0}/{1}".format(endpoint, token),
                params={"base64_encoded": "true"},
                headers=_headers(api_token),
                timeout=10,
            )
        except requests.RequestException as exc:
            raise Judge0Error(
                "Judge0 connection failed: {0}".format(exc.__class__.__name__)
            ) from exc
        if response.status_code >= 400:
            raise Judge0Error("Judge0 returned HTTP {0}".format(response.status_code))
        try:
            last = _decode_body(response.json())
        except ValueError as exc:
            raise Judge0Error("Judge0 returned a non-JSON response") from exc
        status = (last.get("status") or {}).get("id")
        if status not in (STATUS_IN_QUEUE, STATUS_PROCESSING, None):
            return last
        time.sleep(0.4)
    raise Judge0Error("Judge0 timed out waiting for a result")


def classify(result: dict) -> str:
    """Map a Judge0 submission object to a short status name."""
    status = (result or {}).get("status") or {}
    status_id = status.get("id")
    description = status.get("description") or "Internal Error"

    if status_id == STATUS_ACCEPTED:
        return "Accepted"
    if status_id == STATUS_WRONG_ANSWER:
        return "Wrong Answer"
    if status_id == STATUS_TIME_LIMIT:
        return "Time Limit Exceeded"
    if status_id == STATUS_COMPILATION:
        return "Compilation Error"
    if status_id == STATUS_INTERNAL:
        return "Internal Error"
    if status_id in RUNTIME_STATUS_IDS:
        # Keep the specific signal (SIGSEGV, NZEC, ...) for the player.
        if "memory" in description.lower():
            return "Memory Limit Exceeded"
        return description or "Runtime Error"
    if description and "memory" in description.lower():
        return "Memory Limit Exceeded"
    return description or "Internal Error"


def public_fields(result: dict) -> dict:
    """Fields safe to show for a sample run. Never includes stdin or expected."""
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    compile_output = result.get("compile_output") or ""
    return {
        "status": classify(result),
        "status_id": (result.get("status") or {}).get("id"),
        "stdout": stdout,
        "stderr": stderr,
        "compile_output": compile_output,
        "time": result.get("time"),
        "memory": result.get("memory"),
        "message": result.get("message") or "",
    }

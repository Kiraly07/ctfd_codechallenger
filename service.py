"""Request validation and the run/submit orchestration.

Nothing here executes submitted source. Every program goes to Judge0.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from flask import current_app

from CTFd.cache import cache
from CTFd.utils import get_config

from . import client as judge0_client
from .client import Judge0Error, classify, public_fields
from .compare import outputs_match
from .constants import (
    COMPARISON_MODES,
    CONFIG_TOKEN_KEY,
    CONFIG_URL_KEY,
    DEFAULT_COMPARISON,
    DEFAULT_CPU_TIME,
    DEFAULT_MEMORY_KB,
    ENV_TOKEN,
    ENV_URL,
    LANGUAGES,
    MAX_CODE_SIZE,
    MAX_CPU_TIME,
    MAX_INPUT_SIZE,
    MAX_MEMORY_KB,
    MAX_OUTPUT_SIZE,
    MAX_STARTER_SIZE,
    MAX_TEST_CASES,
    MIN_CPU_TIME,
    MIN_MEMORY_KB,
    RUN_PER_MINUTE,
    SUBMIT_PER_MINUTE,
)
from .models import Judge0Challenge, Judge0TestCase

log = logging.getLogger("ctfd.plugins.ctfd_code")


class ValidationError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def resolve_ctfd_code_url(challenge: Judge0Challenge | None = None) -> str:
    """Per-challenge URL, then CTFd config, then JUDGE0_URL. Never a hardcoded IP."""
    if challenge is not None and (challenge.ctfd_code_url or "").strip():
        return challenge.ctfd_code_url.strip()
    configured = get_config(CONFIG_URL_KEY)
    if configured:
        return str(configured).strip()
    return os.environ.get(ENV_URL, "").strip()


def resolve_api_token() -> str:
    """Optional. Local Judge0 without AUTH_TOKEN needs nothing.

    The token is read from CTFd config or the environment and is never
    returned to the browser.
    """
    configured = get_config(CONFIG_TOKEN_KEY)
    if configured:
        return str(configured).strip()
    return os.environ.get(ENV_TOKEN, "").strip()


def clamp_limits(cpu_time_limit, memory_limit) -> tuple[float, int]:
    try:
        cpu = float(cpu_time_limit)
    except (TypeError, ValueError):
        cpu = DEFAULT_CPU_TIME
    try:
        memory = int(memory_limit)
    except (TypeError, ValueError):
        memory = DEFAULT_MEMORY_KB
    cpu = min(max(cpu, MIN_CPU_TIME), MAX_CPU_TIME)
    memory = min(max(memory, MIN_MEMORY_KB), MAX_MEMORY_KB)
    return cpu, memory


def language_for_slug(slug: str, allowed: list[str]) -> tuple[int, str]:
    if not isinstance(slug, str) or slug not in LANGUAGES:
        raise ValidationError("Unknown language")
    if slug not in (allowed or []):
        raise ValidationError("This language is not enabled for the challenge")
    language_id, label, _mode = LANGUAGES[slug]
    return language_id, label


def parse_source(data: dict) -> tuple[str, str]:
    if not isinstance(data, dict):
        raise ValidationError("Expected a JSON object")
    source = data.get("source_code")
    language = data.get("language")
    if not isinstance(source, str) or not source.strip():
        raise ValidationError("source_code is required")
    if len(source.encode("utf-8")) > MAX_CODE_SIZE:
        raise ValidationError("source_code exceeds the size limit")
    if not isinstance(language, str):
        raise ValidationError("language is required")
    return source, language


def check_rate_limit(account_id: int, challenge_id: int, kind: str) -> bool:
    """Return True when the caller is still inside the per-minute budget."""
    limit = RUN_PER_MINUTE if kind == "run" else SUBMIT_PER_MINUTE
    key = "ctfd_code_{0}_{1}_{2}".format(kind, account_id, challenge_id)
    try:
        count = int(cache.inc(key))
    except Exception:
        # Cache failures must not turn into an open gate or a crash.
        log.warning("[CTFD_CODE] rate-limit cache unavailable")
        return True
    if count == 1:
        cache.expire(key, 60)
    return count <= limit


def _run_one(url, token, language_id, source, case, cpu, memory) -> dict:
    if len((case.stdin or "").encode("utf-8")) > MAX_INPUT_SIZE:
        raise ValidationError("A test case exceeds the input size limit")
    result = judge0_client.submit(
        url=url,
        api_token=token,
        language_id=language_id,
        source_code=source,
        stdin=case.stdin or "",
        cpu_time_limit=cpu,
        memory_limit=memory,
    )
    fields = public_fields(result)
    status_name = fields["status"]
    # Judge0 "Accepted" only means the process exited 0. Correctness is local.
    if status_name == "Accepted":
        stdout = fields["stdout"] or ""
        if len(stdout.encode("utf-8")) > MAX_OUTPUT_SIZE:
            stdout = stdout.encode("utf-8")[:MAX_OUTPUT_SIZE].decode("utf-8", "ignore")
            fields["stdout"] = stdout
        passed = outputs_match(stdout, case.expected_output or "", mode=_mode_of(case))
        fields["passed"] = passed
        if not passed:
            fields["status"] = "Wrong Answer"
    else:
        fields["passed"] = False
    return fields


def _mode_of(case: Judge0TestCase) -> str:
    challenge = case.challenge
    mode = getattr(challenge, "comparison_mode", DEFAULT_COMPARISON)
    if mode not in COMPARISON_MODES:
        return DEFAULT_COMPARISON
    return mode


def run_samples(challenge: Judge0Challenge, source: str, language_slug: str) -> dict:
    language_id, label = language_for_slug(language_slug, challenge.allowed_languages or [])
    samples = [case for case in challenge.test_cases if case.is_sample]
    if not samples:
        raise ValidationError("This challenge has no sample test cases to run")

    url = resolve_ctfd_code_url(challenge)
    if not url:
        raise ValidationError("Judge0 URL is not configured")
    token = resolve_api_token()
    cpu, memory = clamp_limits(challenge.cpu_time_limit, challenge.memory_limit)

    log.info(
        "[CTFD_CODE] submitting challenge_id=%s language_id=%s cases=%s kind=run",
        challenge.id,
        language_id,
        len(samples),
    )

    results = []
    for case in samples:
        try:
            fields = _run_one(url, token, language_id, source, case, cpu, memory)
        except Judge0Error as exc:
            log.warning("[CTFD_CODE] challenge_id=%s error=%s", challenge.id, exc)
            raise
        log.info(
            "[CTFD_CODE] challenge_id=%s language_id=%s result_status=%s",
            challenge.id,
            language_id,
            fields["status"],
        )
        results.append(
            {
                "name": case.name or "Sample {0}".format(case.position + 1),
                "stdin": case.stdin or "",
                "expected_output": case.expected_output or "",
                "passed": fields["passed"],
                "status": fields["status"],
                "stdout": fields["stdout"],
                "stderr": fields["stderr"],
                "compile_output": fields["compile_output"],
                "time": fields["time"],
                "memory": fields["memory"],
            }
        )

    passed = sum(1 for item in results if item["passed"])
    overall = _overall_status(results)
    return {
        "success": overall == "Accepted",
        "status": overall,
        "language": label,
        "passed": passed,
        "total": len(results),
        "cases": results,
    }


def grade_all(challenge: Judge0Challenge, source: str, language_slug: str) -> dict:
    """Grade every test case. Hidden input and expected output stay here."""
    language_id, label = language_for_slug(language_slug, challenge.allowed_languages or [])
    cases = list(challenge.test_cases)
    if not cases:
        raise ValidationError("This challenge has no test cases")

    url = resolve_ctfd_code_url(challenge)
    if not url:
        raise ValidationError("Judge0 URL is not configured")
    token = resolve_api_token()
    cpu, memory = clamp_limits(challenge.cpu_time_limit, challenge.memory_limit)

    log.info(
        "[CTFD_CODE] submitting challenge_id=%s language_id=%s cases=%s kind=submit",
        challenge.id,
        language_id,
        len(cases),
    )

    public_cases = []
    passed = 0
    first_failure = None
    for index, case in enumerate(cases):
        try:
            fields = _run_one(url, token, language_id, source, case, cpu, memory)
        except Judge0Error as exc:
            log.warning("[CTFD_CODE] challenge_id=%s error=%s", challenge.id, exc)
            raise
        log.info(
            "[CTFD_CODE] challenge_id=%s language_id=%s result_status=%s",
            challenge.id,
            language_id,
            fields["status"],
        )
        if fields["passed"]:
            passed += 1
        elif first_failure is None:
            first_failure = fields["status"]

        # Sample rows may include input, expected output and program output.
        # Hidden rows only say pass/fail and the status name.
        if case.is_sample:
            public_cases.append(
                {
                    "name": case.name or "Sample {0}".format(index + 1),
                    "sample": True,
                    "stdin": case.stdin or "",
                    "expected_output": case.expected_output or "",
                    "passed": fields["passed"],
                    "status": fields["status"],
                    "stdout": fields["stdout"],
                    "stderr": fields["stderr"],
                    "compile_output": fields["compile_output"],
                    "time": fields["time"],
                    "memory": fields["memory"],
                }
            )
        else:
            public_cases.append(
                {
                    "name": "Hidden {0}".format(index + 1),
                    "sample": False,
                    "passed": fields["passed"],
                    "status": fields["status"],
                }
            )

    overall = "Accepted" if passed == len(cases) else (first_failure or "Wrong Answer")
    return {
        "success": overall == "Accepted",
        "status": overall,
        "language": label,
        "passed": passed,
        "total": len(cases),
        "cases": public_cases,
    }


def _overall_status(results: list[dict]) -> str:
    if results and all(item["passed"] for item in results):
        return "Accepted"
    for item in results:
        if not item["passed"]:
            return item["status"]
    return "Wrong Answer"


def sanitize_languages(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValidationError("Select at least one language")
    cleaned = []
    for slug in value:
        if slug not in LANGUAGES:
            raise ValidationError("Unknown language: {0}".format(slug))
        if slug not in cleaned:
            cleaned.append(slug)
    return cleaned


def sanitize_starter(value: Any, allowed: list[str]) -> dict:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValidationError("starter_code must be an object")
    cleaned = {}
    for slug, source in value.items():
        if slug not in allowed:
            continue
        if not isinstance(source, str):
            raise ValidationError("starter_code values must be strings")
        if len(source.encode("utf-8")) > MAX_STARTER_SIZE:
            raise ValidationError("starter code is too large")
        if source:
            cleaned[slug] = source
    return cleaned


def sanitize_comparison(value: Any) -> str:
    if value in (None, ""):
        return DEFAULT_COMPARISON
    if value not in COMPARISON_MODES:
        raise ValidationError("Unknown comparison mode")
    return value


def sanitize_url(value: Any) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise ValidationError("Judge0 URL must be a string")
    value = value.strip()
    if len(value) > 255:
        raise ValidationError("Judge0 URL is too long")
    if value and not (value.startswith("http://") or value.startswith("https://")):
        raise ValidationError("Judge0 URL must start with http:// or https://")
    return value


def testcase_count_ok(count: int) -> None:
    if count > MAX_TEST_CASES:
        raise ValidationError("A challenge can have at most {0} test cases".format(MAX_TEST_CASES))


def public_challenge_config(challenge: Judge0Challenge) -> dict:
    """Fields the player UI needs. No URL, no token, no hidden cases."""
    samples = []
    for case in challenge.test_cases:
        if not case.is_sample:
            continue
        samples.append(
            {
                "name": case.name or "",
                "stdin": case.stdin or "",
                "expected_output": case.expected_output or "",
            }
        )
    allowed = [slug for slug in (challenge.allowed_languages or []) if slug in LANGUAGES]
    return {
        "languages": [
            {"slug": slug, "label": LANGUAGES[slug][1], "mode": LANGUAGES[slug][2]}
            for slug in allowed
        ],
        "starter_code": {
            slug: (challenge.starter_code or {}).get(slug, "")
            for slug in allowed
        },
        "samples": samples,
        "comparison_mode": challenge.comparison_mode or DEFAULT_COMPARISON,
        "cpu_time_limit": challenge.cpu_time_limit,
        "memory_limit": challenge.memory_limit,
    }


def log_app_prefix() -> str:
    try:
        return current_app.name
    except Exception:
        return "ctfd"

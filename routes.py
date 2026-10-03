"""HTTP routes for the Judge0 plugin.

Player:
    GET  /plugins/judge0/<challenge_id>/config
    POST /plugins/judge0/run/<challenge_id>
    POST /plugins/judge0/submit/<challenge_id>

Admin:
    GET/POST        /plugins/judge0/admin/<challenge_id>/tests
    PATCH/DELETE    /plugins/judge0/admin/tests/<test_id>
    GET/POST        /plugins/judge0/admin/settings

CSRF is the normal CTFd check: JSON requests must send CSRF-Token, which
CTFd.fetch already does. These routes do not bypass it.
"""

from __future__ import annotations

import logging

from flask import Blueprint, abort, render_template, request

from CTFd.cache import clear_challenges, clear_standings
from CTFd.exceptions.challenges import ChallengeSolveException
from CTFd.models import Challenges, Solves, db
from CTFd.utils import get_config, set_config
from CTFd.utils.config import is_teams_mode
from CTFd.utils.dates import ctf_paused, ctftime
from CTFd.utils.decorators import admins_only, authed_only
from CTFd.utils.user import get_current_team, get_current_user, is_admin

from .challenge import Judge0CodeChallenge
from .client import Judge0Error
from .constants import CONFIG_TOKEN_KEY, CONFIG_URL_KEY, LANGUAGES, MAX_TEST_CASES
from .models import Judge0Challenge, Judge0TestCase
from .service import (
    ValidationError,
    check_rate_limit,
    grade_all,
    parse_source,
    public_challenge_config,
    resolve_judge0_url,
    run_samples,
    sanitize_url,
    testcase_count_ok,
)

log = logging.getLogger("ctfd.plugins.judge0")

judge0_bp = Blueprint("judge0", __name__)


def _load_player_challenge(challenge_id: int) -> Judge0Challenge:
    challenge = Judge0Challenge.query.filter_by(id=challenge_id).first()
    if challenge is None:
        # Distinguish "not this type" from "missing" without leaking hidden rows.
        other = Challenges.query.filter_by(id=challenge_id).first()
        if other is None or other.state == "hidden":
            abort(404)
        abort(400)
    if not is_admin():
        if challenge.state == "hidden":
            abort(404)
        if challenge.state == "locked":
            abort(403)
    return challenge


def _require_player():
    user = get_current_user()
    team = get_current_team()
    if user is None:
        abort(403)
    if is_teams_mode() and team is None and not user.is_admin():
        abort(403)
    return user, team


def _json_body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400)
    return data


def _error(message: str, code: int = 400):
    return {"success": False, "status": "Error", "message": message}, code


def _case_payload(data: dict) -> dict:
    stdin = data.get("stdin", "")
    expected = data.get("expected_output", "")
    name = data.get("name", "")
    if not isinstance(stdin, str) or not isinstance(expected, str):
        raise ValidationError("stdin and expected_output must be strings")
    if not isinstance(name, str):
        raise ValidationError("name must be a string")
    if len(name) > 80:
        raise ValidationError("name is too long")
    if len(stdin.encode("utf-8")) > 65535 or len(expected.encode("utf-8")) > 65535:
        raise ValidationError("test case is too large")
    is_sample = bool(data.get("is_sample"))
    return {
        "stdin": stdin,
        "expected_output": expected,
        "name": name.strip(),
        "is_sample": is_sample,
    }


@judge0_bp.route("/plugins/judge0/<int:challenge_id>/config", methods=["GET"])
@authed_only
def player_config(challenge_id):
    challenge = _load_player_challenge(challenge_id)
    return {"success": True, "data": public_challenge_config(challenge)}


def _competition_open() -> bool:
    """JSON-friendly stand-in for during_ctf_time_only.

    That decorator redirects to HTML when the CTF has not started, which
    breaks a fetch() client. Admins may run and submit outside the window
    so they can test a challenge before it opens.
    """
    if is_admin():
        return True
    if ctf_paused():
        return False
    return bool(ctftime())


@judge0_bp.route("/plugins/judge0/run/<int:challenge_id>", methods=["POST"])
@authed_only
def run_code(challenge_id):
    """Run sample tests only. Does not solve, fail, or award points."""
    if not _competition_open():
        return _error("Submissions are closed right now.", 403)
    user, _team = _require_player()
    challenge = _load_player_challenge(challenge_id)
    if not check_rate_limit(user.account_id, challenge.id, "run"):
        return _error("Too many runs. Wait a moment and try again.", 429)

    data = _json_body()
    try:
        source, language = parse_source(data)
        result = run_samples(challenge, source, language)
    except ValidationError as exc:
        return _error(exc.message, 400)
    except Judge0Error as exc:
        log.warning("[JUDGE0] run challenge_id=%s error=%s", challenge.id, exc)
        return _error("Judge0 could not run this code. Check the server URL.", 502)

    # A single-sample challenge gets the flat shape the spec shows, plus the
    # per-case list so the console can render every sample.
    first = result["cases"][0] if result["cases"] else {}
    return {
        "success": True,
        "solved": False,
        "status": result["status"],
        "passed": result["passed"],
        "total": result["total"],
        "stdout": first.get("stdout", ""),
        "stderr": first.get("stderr", ""),
        "compile_output": first.get("compile_output", ""),
        "time": first.get("time"),
        "memory": first.get("memory"),
        "cases": result["cases"],
    }


@judge0_bp.route("/plugins/judge0/submit/<int:challenge_id>", methods=["POST"])
@authed_only
def submit_code(challenge_id):
    """Grade every test case. A full pass records a CTFd solve."""
    if not _competition_open():
        return _error("Submissions are closed right now.", 403)
    user, team = _require_player()
    challenge = _load_player_challenge(challenge_id)

    if not check_rate_limit(user.account_id, challenge.id, "submit"):
        return _error("Too many submissions. Wait a moment and try again.", 429)

    already = Solves.query.filter_by(
        account_id=user.account_id, challenge_id=challenge.id
    ).first()

    data = _json_body()
    try:
        source, language = parse_source(data)
        result = grade_all(challenge, source, language)
    except ValidationError as exc:
        return _error(exc.message, 400)
    except Judge0Error as exc:
        log.warning("[JUDGE0] submit challenge_id=%s error=%s", challenge.id, exc)
        return _error("Judge0 could not grade this submission.", 502)

    # Attach language so solve()/fail() can store a short marker, not the source.
    # The core attempt logger reads request JSON; we do not log source ourselves.
    # Record a solve or a fail only while the CTF is running, matching the
    # core attempt endpoint. Admins may still record a solve so they can
    # verify scoring before the event opens.
    record = already is None and (ctftime() or user.is_admin())
    if result["success"]:
        if record:
            try:
                Judge0CodeChallenge.solve(
                    user=user, team=team, challenge=challenge, request=request
                )
            except ChallengeSolveException:
                pass
            except Exception:
                log.exception("[JUDGE0] solve failed challenge_id=%s", challenge.id)
                return _error("The solution passed but could not be recorded.", 500)
            clear_standings()
            clear_challenges()
        status_name = "Accepted"
        message = "Accepted ({0}/{1} tests)".format(result["passed"], result["total"])
    else:
        if record:
            Judge0CodeChallenge.fail(
                user=user, team=team, challenge=challenge, request=request
            )
            clear_standings()
            clear_challenges()
        status_name = result["status"]
        message = "{0} ({1}/{2} tests)".format(
            result["status"], result["passed"], result["total"]
        )

    return {
        "success": result["success"],
        "solved": result["success"],
        "status": status_name,
        "message": message,
        "passed": result["passed"],
        "total": result["total"],
        "cases": result["cases"],
    }


@judge0_bp.route("/plugins/judge0/admin/<int:challenge_id>/tests", methods=["GET"])
@admins_only
def list_tests(challenge_id):
    challenge = Judge0Challenge.query.filter_by(id=challenge_id).first_or_404()
    return {
        "success": True,
        "data": Judge0CodeChallenge.read(challenge)["test_cases"],
    }


@judge0_bp.route("/plugins/judge0/admin/<int:challenge_id>/tests", methods=["POST"])
@admins_only
def create_test(challenge_id):
    challenge = Judge0Challenge.query.filter_by(id=challenge_id).first_or_404()
    try:
        testcase_count_ok(len(challenge.test_cases) + 1)
        fields = _case_payload(_json_body())
    except ValidationError as exc:
        return _error(exc.message, 400)

    position = max([case.position for case in challenge.test_cases], default=-1) + 1
    case = Judge0TestCase(
        challenge_id=challenge.id,
        position=position,
        **fields,
    )
    db.session.add(case)
    db.session.commit()
    return {"success": True, "data": {"id": case.id, "position": case.position}}


@judge0_bp.route("/plugins/judge0/admin/tests/<int:test_id>", methods=["PATCH"])
@admins_only
def update_test(test_id):
    case = Judge0TestCase.query.filter_by(id=test_id).first_or_404()
    data = _json_body()
    try:
        fields = _case_payload(
            {
                "stdin": data.get("stdin", case.stdin),
                "expected_output": data.get("expected_output", case.expected_output),
                "name": data.get("name", case.name),
                "is_sample": data.get("is_sample", case.is_sample),
            }
        )
    except ValidationError as exc:
        return _error(exc.message, 400)

    case.stdin = fields["stdin"]
    case.expected_output = fields["expected_output"]
    case.name = fields["name"]
    case.is_sample = fields["is_sample"]
    if "position" in data:
        try:
            case.position = int(data["position"])
        except (TypeError, ValueError):
            return _error("position must be an integer", 400)
    db.session.commit()
    return {"success": True}


@judge0_bp.route("/plugins/judge0/admin/tests/<int:test_id>", methods=["DELETE"])
@admins_only
def delete_test(test_id):
    case = Judge0TestCase.query.filter_by(id=test_id).first_or_404()
    db.session.delete(case)
    db.session.commit()
    return {"success": True}


@judge0_bp.route("/plugins/judge0/admin/settings", methods=["GET"])
@admins_only
def settings_page():
    # HTML for the nav item. The JSON API lives at /plugins/judge0/admin/settings.json
    # so this path can be a normal admin page.
    return render_template("plugins/judge0/assets/admin_settings.html")


@judge0_bp.route("/plugins/judge0/admin/settings.json", methods=["GET"])
@admins_only
def get_settings():
    # The token is write-only. The response says whether one is set, not the value.
    token = get_config(CONFIG_TOKEN_KEY) or ""
    return {
        "success": True,
        "data": {
            "judge0_url": get_config(CONFIG_URL_KEY) or "",
            "token_set": bool(token),
            "languages": [
                {"slug": slug, "id": meta[0], "label": meta[1]}
                for slug, meta in LANGUAGES.items()
            ],
            "effective_url": resolve_judge0_url(None),
            "max_test_cases": MAX_TEST_CASES,
        },
    }


@judge0_bp.route("/plugins/judge0/admin/settings", methods=["POST"])
@admins_only
def save_settings():
    data = _json_body()
    try:
        url = sanitize_url(data.get("judge0_url", ""))
    except ValidationError as exc:
        return _error(exc.message, 400)
    set_config(CONFIG_URL_KEY, url)
    if "api_token" in data and data["api_token"] not in (None, ""):
        token = data["api_token"]
        if not isinstance(token, str) or len(token) > 255:
            return _error("API token is invalid", 400)
        set_config(CONFIG_TOKEN_KEY, token.strip())
    if data.get("clear_token"):
        set_config(CONFIG_TOKEN_KEY, "")
    return {"success": True}

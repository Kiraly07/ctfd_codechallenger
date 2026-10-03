"""Judge0 challenge type.

Registered as CHALLENGE_CLASSES['judge0']. CTFd calls create/read/update/
delete for admin CRUD and attempt/solve/fail when a player submits through
POST /api/v1/challenges/attempt.

The player UI does not use that attempt endpoint. It posts source code to
the plugin routes, which grade against Judge0 and, on a full pass, call
solve() through the same models CTFd uses. attempt() still exists so the
standard flag form and admin preview cannot crash, and so a correct
submission that does arrive through the core endpoint is graded too.
"""

from __future__ import annotations

import logging

from flask import Blueprint, request
from sqlalchemy.exc import IntegrityError

from CTFd.exceptions.challenges import (
    ChallengeCreateException,
    ChallengeSolveException,
    ChallengeUpdateException,
)
from CTFd.models import (
    ChallengeFiles,
    Challenges,
    Fails,
    Flags,
    Hints,
    SolutionFiles,
    Solutions,
    SolutionUnlocks,
    Solves,
    Tags,
    db,
)
from CTFd.plugins.challenges import BaseChallenge
from CTFd.utils.dates import parse_iso_datetime
from CTFd.utils.uploads import delete_file
from CTFd.utils.user import get_ip

from .constants import (
    DEFAULT_COMPARISON,
    DEFAULT_CPU_TIME,
    DEFAULT_LANGUAGES,
    DEFAULT_MEMORY_KB,
)
from .models import Judge0Challenge, Judge0TestCase
from .service import (
    ValidationError,
    clamp_limits,
    grade_all,
    sanitize_comparison,
    sanitize_languages,
    sanitize_starter,
    sanitize_url,
)

log = logging.getLogger("ctfd.plugins.judge0")

# Columns that belong on the parent Challenges row. Anything else in the
# admin JSON is either a Judge0 column or ignored.
_PARENT_FIELDS = {
    "name",
    "description",
    "attribution",
    "connection_info",
    "next_id",
    "max_attempts",
    "value",
    "category",
    "type",
    "state",
    "logic",
    "position",
    "scheduled_at",
    "requirements",
    "module_id",
    "function",
}

_JUDGE0_FIELDS = {
    "judge0_url",
    "cpu_time_limit",
    "memory_limit",
    "allowed_languages",
    "starter_code",
    "comparison_mode",
}


def _clean_create_payload(data: dict) -> dict:
    """Drop keys that are not columns. The admin form only sends parent fields
    plus type; Judge0 columns get defaults in the model constructor.
    """
    cleaned = {}
    for key, value in data.items():
        if key in _PARENT_FIELDS or key in _JUDGE0_FIELDS:
            cleaned[key] = value
    if "value" in cleaned and cleaned["value"] not in (None, ""):
        try:
            cleaned["value"] = int(cleaned["value"])
        except (TypeError, ValueError):
            raise ChallengeCreateException("Value must be an integer")
    if "scheduled_at" in cleaned:
        try:
            cleaned["scheduled_at"] = parse_iso_datetime(cleaned["scheduled_at"])
        except ValueError:
            raise ChallengeCreateException(
                "Invalid 'scheduled_at' — expected ISO 8601 datetime"
            )
    cleaned["type"] = "judge0"
    # Static scoring. Dynamic decay columns stay unused.
    cleaned.setdefault("function", "static")
    cleaned.setdefault("state", "hidden")
    return cleaned


def _apply_judge0_fields(challenge: Judge0Challenge, data: dict) -> None:
    if "judge0_url" in data:
        try:
            challenge.judge0_url = sanitize_url(data.get("judge0_url"))
        except ValidationError as exc:
            raise ChallengeUpdateException(str(exc)) from exc

    if "cpu_time_limit" in data or "memory_limit" in data:
        cpu, memory = clamp_limits(
            data.get("cpu_time_limit", challenge.cpu_time_limit),
            data.get("memory_limit", challenge.memory_limit),
        )
        if "cpu_time_limit" in data:
            challenge.cpu_time_limit = cpu
        if "memory_limit" in data:
            challenge.memory_limit = memory

    if "allowed_languages" in data:
        try:
            challenge.allowed_languages = sanitize_languages(data.get("allowed_languages"))
        except ValidationError as exc:
            raise ChallengeUpdateException(str(exc)) from exc

    if "comparison_mode" in data:
        try:
            challenge.comparison_mode = sanitize_comparison(data.get("comparison_mode"))
        except ValidationError as exc:
            raise ChallengeUpdateException(str(exc)) from exc

    if "starter_code" in data:
        try:
            challenge.starter_code = sanitize_starter(
                data.get("starter_code"),
                challenge.allowed_languages or list(DEFAULT_LANGUAGES),
            )
        except ValidationError as exc:
            raise ChallengeUpdateException(str(exc)) from exc


class Judge0CodeChallenge(BaseChallenge):
    id = "judge0"
    name = "Judge0 Code Challenge"
    templates = {
        "create": "/plugins/judge0/assets/create.html",
        "update": "/plugins/judge0/assets/update.html",
        "view": "/plugins/judge0/assets/view.html",
    }
    scripts = {
        "create": "/plugins/judge0/assets/create.js",
        "update": "/plugins/judge0/assets/update.js",
        "view": "/plugins/judge0/assets/view.js",
    }
    route = "/plugins/judge0/assets/"
    blueprint = Blueprint(
        "judge0_challenge",
        __name__,
        template_folder="assets",
        static_folder="assets",
    )
    challenge_model = Judge0Challenge

    @classmethod
    def create(cls, request):
        data = dict(request.form or request.get_json() or {})
        try:
            payload = _clean_create_payload(data)
        except ChallengeCreateException:
            raise
        except ValidationError as exc:
            raise ChallengeCreateException(str(exc)) from exc

        # Judge0-specific keys are not constructor arguments of Challenges
        # in every CTFd patch, so set them after the row exists.
        judge0_keys = {key: payload.pop(key) for key in list(payload) if key in _JUDGE0_FIELDS}

        challenge = Judge0Challenge(**payload)
        db.session.add(challenge)
        db.session.flush()
        if judge0_keys:
            _apply_judge0_fields(challenge, judge0_keys)
        else:
            challenge.allowed_languages = list(DEFAULT_LANGUAGES)
            challenge.starter_code = {}
            challenge.comparison_mode = DEFAULT_COMPARISON
            challenge.cpu_time_limit = DEFAULT_CPU_TIME
            challenge.memory_limit = DEFAULT_MEMORY_KB
            challenge.judge0_url = ""
        db.session.commit()
        return challenge

    @classmethod
    def read(cls, challenge):
        challenge = Judge0Challenge.query.filter_by(id=challenge.id).first()
        data = super().read(challenge)
        data.update(
            {
                "judge0_url": challenge.judge0_url or "",
                "cpu_time_limit": challenge.cpu_time_limit,
                "memory_limit": challenge.memory_limit,
                "allowed_languages": challenge.allowed_languages or [],
                "starter_code": challenge.starter_code or {},
                "comparison_mode": challenge.comparison_mode or DEFAULT_COMPARISON,
            }
        )
        # Test cases (including hidden expected output) are admin-only.
        # The public challenge GET uses this same read(), so the list is
        # attached only for an authenticated admin.
        from CTFd.utils.user import is_admin

        if is_admin():
            data["test_cases"] = [
                {
                    "id": case.id,
                    "position": case.position,
                    "name": case.name or "",
                    "stdin": case.stdin or "",
                    "expected_output": case.expected_output or "",
                    "is_sample": bool(case.is_sample),
                }
                for case in challenge.test_cases
            ]
        return data

    @classmethod
    def update(cls, challenge, request):
        data = dict(request.form or request.get_json() or {})
        challenge = Judge0Challenge.query.filter_by(id=challenge.id).first()

        if "scheduled_at" in data:
            try:
                data["scheduled_at"] = parse_iso_datetime(data["scheduled_at"])
            except ValueError:
                raise ChallengeUpdateException("Invalid input for 'scheduled_at'")

        for attr, value in data.items():
            if attr not in _PARENT_FIELDS:
                continue
            if attr == "type":
                continue
            if attr == "value" and value is not None:
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    raise ChallengeUpdateException("Value must be an integer")
            setattr(challenge, attr, value)

        try:
            _apply_judge0_fields(challenge, data)
        except ChallengeUpdateException:
            db.session.rollback()
            raise

        db.session.commit()
        return challenge

    @classmethod
    def delete(cls, challenge):
        # Test cases go first so the FK does not block the parent delete on
        # engines that are mid-migration. The FK itself is ON DELETE CASCADE.
        Judge0TestCase.query.filter_by(challenge_id=challenge.id).delete()
        Fails.query.filter_by(challenge_id=challenge.id).delete()
        Solves.query.filter_by(challenge_id=challenge.id).delete()
        Flags.query.filter_by(challenge_id=challenge.id).delete()
        files = ChallengeFiles.query.filter_by(challenge_id=challenge.id).all()
        for f in files:
            delete_file(f.id)
        ChallengeFiles.query.filter_by(challenge_id=challenge.id).delete()
        Tags.query.filter_by(challenge_id=challenge.id).delete()
        Hints.query.filter_by(challenge_id=challenge.id).delete()
        solution = Solutions.query.filter_by(challenge_id=challenge.id).first()
        if solution:
            solution_files = SolutionFiles.query.filter_by(solution_id=solution.id).all()
            for f in solution_files:
                delete_file(f.id)
            SolutionUnlocks.query.filter_by(target=solution.id).delete()
            Solutions.query.filter_by(id=solution.id).delete()
        Judge0Challenge.query.filter_by(id=challenge.id).delete()
        Challenges.query.filter_by(id=challenge.id).delete()
        db.session.commit()

    @classmethod
    def attempt(cls, challenge, request):
        """Grade a submission that arrived through CTFd's attempt endpoint.

        The player UI posts to /plugins/judge0/submit instead, because the
        core endpoint stores the raw submission string and expects a flag.
        This method still grades source_code when it is present so admin
        preview and API clients behave the same way.
        """
        data = request.get_json(silent=True) or request.form or {}
        source = data.get("source_code") or data.get("submission") or ""
        language = data.get("language") or ""
        if not source or not language:
            return False, "Submit your code with the Submit button"

        challenge = Judge0Challenge.query.filter_by(id=challenge.id).first()
        try:
            result = grade_all(challenge, source, language)
        except ValidationError as exc:
            return False, exc.message
        except Exception:
            log.exception("[JUDGE0] attempt failed challenge_id=%s", challenge.id)
            return False, "Judge0 could not grade this submission"

        if result["success"]:
            return True, "Accepted ({0}/{1} tests)".format(result["passed"], result["total"])
        return False, "{0} ({1}/{2} tests)".format(
            result["status"], result["passed"], result["total"]
        )

    @classmethod
    def solve(cls, user, team, challenge, request):
        data = request.get_json(silent=True) or request.form or {}
        # Never store the source. A short marker is enough for the solves table.
        language = data.get("language") or ""
        provided = "judge0:{0}".format(language)[:128]
        solve = Solves(
            user_id=user.id,
            team_id=team.id if team else None,
            challenge_id=challenge.id,
            ip=get_ip(req=request),
            provided=provided,
        )
        try:
            db.session.add(solve)
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            raise ChallengeSolveException(
                "Duplicate solve for user {0} on challenge {1}".format(user.id, challenge.id)
            ) from exc

    @classmethod
    def fail(cls, user, team, challenge, request):
        data = request.get_json(silent=True) or request.form or {}
        language = data.get("language") or ""
        provided = "judge0:{0}".format(language)[:128]
        wrong = Fails(
            user_id=user.id,
            team_id=team.id if team else None,
            challenge_id=challenge.id,
            ip=get_ip(request),
            provided=provided,
        )
        db.session.add(wrong)
        db.session.commit()

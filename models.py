"""SQLAlchemy models for the Judge0 challenge type.

Joined-table inheritance, same pattern as CTFd's dynamic challenge:
Judge0Challenge extends Challenges and Judge0TestCase hangs off it.
"""

from __future__ import annotations

from CTFd.models import Challenges, db

from .constants import (
    DEFAULT_COMPARISON,
    DEFAULT_CPU_TIME,
    DEFAULT_LANGUAGES,
    DEFAULT_MEMORY_KB,
)


class Judge0Challenge(Challenges):
    __mapper_args__ = {"polymorphic_identity": "ctfd_code"}
    __tablename__ = "ctfd_code_challenge"

    id = db.Column(
        db.Integer,
        db.ForeignKey("challenges.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Empty string means "use the global plugin URL".
    ctfd_code_url = db.Column(db.String(255), nullable=False, default="")
    cpu_time_limit = db.Column(db.Float, nullable=False, default=DEFAULT_CPU_TIME)
    memory_limit = db.Column(db.Integer, nullable=False, default=DEFAULT_MEMORY_KB)
    # JSON list of language slugs, e.g. ["python3", "cpp"].
    allowed_languages = db.Column(db.JSON, nullable=False, default=list)
    # JSON object slug -> starter source. Never required.
    starter_code = db.Column(db.JSON, nullable=False, default=dict)
    comparison_mode = db.Column(
        db.String(32), nullable=False, default=DEFAULT_COMPARISON
    )

    test_cases = db.relationship(
        "Judge0TestCase",
        backref="challenge",
        cascade="all, delete-orphan",
        order_by="Judge0TestCase.position",
        lazy="select",
    )

    def __init__(self, *args, **kwargs):
        # SQLAlchemy passes every Challenges column through kwargs. Extra
        # keys that are not columns must be pulled out first.
        kwargs.setdefault("allowed_languages", list(DEFAULT_LANGUAGES))
        kwargs.setdefault("starter_code", {})
        kwargs.setdefault("comparison_mode", DEFAULT_COMPARISON)
        kwargs.setdefault("cpu_time_limit", DEFAULT_CPU_TIME)
        kwargs.setdefault("memory_limit", DEFAULT_MEMORY_KB)
        kwargs.setdefault("ctfd_code_url", "")
        super(Judge0Challenge, self).__init__(**kwargs)


class Judge0TestCase(db.Model):
    __tablename__ = "ctfd_code_test_case"

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer,
        db.ForeignKey("ctfd_code_challenge.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position = db.Column(db.Integer, nullable=False, default=0)
    # Optional label shown to the player for sample cases only.
    name = db.Column(db.String(80), nullable=False, default="")
    stdin = db.Column(db.Text, nullable=False, default="")
    expected_output = db.Column(db.Text, nullable=False, default="")
    # Sample cases are the only ones whose input is sent to the browser.
    # Expected output of a sample is also visible. Hidden cases stay server-side.
    is_sample = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return "<Judge0TestCase id={0} challenge={1}>".format(
            self.id, self.challenge_id
        )

import pytest

from app.models import IncidentStatus as S
from app.services.lifecycle import TRANSITIONS, can_transition


def test_happy_path_is_allowed():
    path = [
        S.REPORTED,
        S.TRIAGED,
        S.UNDER_INVESTIGATION,
        S.PENDING_APPROVAL,
        S.ACTION_IN_PROGRESS,
        S.PENDING_VERIFICATION,
        S.CLOSED,
    ]
    for a, b in zip(path, path[1:], strict=False):
        assert can_transition(a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (S.REPORTED, S.CLOSED),
        (S.TRIAGED, S.CLOSED),
        (S.PENDING_APPROVAL, S.CLOSED),
        (S.ACTION_IN_PROGRESS, S.CLOSED),
        (S.REPORTED, S.ACTION_IN_PROGRESS),
        (S.CLOSED, S.PENDING_VERIFICATION),
    ],
)
def test_shortcuts_rejected(a, b):
    assert not can_transition(a, b)


def test_closed_only_from_pending_verification():
    sources = [a for a, targets in TRANSITIONS.items() if S.CLOSED in targets]
    assert sources == [S.PENDING_VERIFICATION]

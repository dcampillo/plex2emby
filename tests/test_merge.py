from datetime import UTC, datetime

import pytest

from plex2emby.merge import combine_sources, merge
from plex2emby.models import ResumePolicy, WatchState

MARCH = datetime(2026, 3, 1, tzinfo=UTC)
MAY = datetime(2026, 5, 3, tzinfo=UTC)
MIN = 600_000_000  # ticks per minute


def test_plex_history_lands_on_an_empty_emby_item():
    source = WatchState(played=True, last_played=MARCH, play_count=2, resume_ticks=40 * MIN)

    assert merge(source, WatchState(), ResumePolicy.FURTHEST) == source


def test_played_on_emby_stays_played_when_plex_is_unplayed():
    target = WatchState(played=True, play_count=1)

    assert merge(WatchState(), target, ResumePolicy.FURTHEST).played is True


def test_later_emby_date_is_kept():
    merged = merge(
        WatchState(played=True, last_played=MARCH),
        WatchState(played=True, last_played=MAY),
        ResumePolicy.FURTHEST,
    )

    assert merged.last_played == MAY


def test_later_plex_date_replaces_emby_date():
    merged = merge(
        WatchState(played=True, last_played=MAY),
        WatchState(played=True, last_played=MARCH),
        ResumePolicy.FURTHEST,
    )

    assert merged.last_played == MAY


def test_undated_plex_play_does_not_invent_a_date():
    merged = merge(WatchState(played=True, play_count=1), WatchState(), ResumePolicy.FURTHEST)

    assert merged.last_played is None


def test_highest_play_count_wins():
    merged = merge(WatchState(play_count=3), WatchState(play_count=5), ResumePolicy.FURTHEST)

    assert merged.play_count == 5


@pytest.mark.parametrize(
    ("policy", "plex_minutes", "emby_minutes", "expected_minutes"),
    [
        (ResumePolicy.FURTHEST, 40, 70, 70),
        (ResumePolicy.FURTHEST, 70, 40, 70),
        (ResumePolicy.FURTHEST, 40, 0, 40),
        (ResumePolicy.SOURCE, 40, 70, 40),
        (ResumePolicy.SOURCE, 0, 70, 0),
        (ResumePolicy.SKIP, 70, 40, 40),
    ],
)
def test_resume_policy(policy, plex_minutes, emby_minutes, expected_minutes):
    merged = merge(
        WatchState(resume_ticks=plex_minutes * MIN),
        WatchState(resume_ticks=emby_minutes * MIN),
        policy,
    )

    assert merged.resume_ticks == expected_minutes * MIN


@pytest.mark.parametrize("policy", list(ResumePolicy))
def test_every_policy_stays_additive_outside_resume_position(policy):
    target = WatchState(played=True, last_played=MAY, play_count=4)

    merged = merge(WatchState(last_played=MARCH, play_count=1), target, policy)

    assert (merged.played, merged.last_played, merged.play_count) == (True, MAY, 4)


def test_duplicate_plex_items_combine_to_latest_highest_and_furthest():
    combined = combine_sources(
        [
            WatchState(played=True, last_played=MARCH, play_count=3, resume_ticks=10 * MIN),
            WatchState(played=False, last_played=MAY, play_count=1, resume_ticks=50 * MIN),
        ]
    )

    assert combined == WatchState(
        played=True, last_played=MAY, play_count=3, resume_ticks=50 * MIN
    )

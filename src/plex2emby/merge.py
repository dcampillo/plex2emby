"""Rules for combining Watch State. Everything is additive except a Source Resume Policy."""

from collections.abc import Iterable
from datetime import datetime

from plex2emby.models import ResumePolicy, WatchState


def _latest(*dates: datetime | None) -> datetime | None:
    return max((d for d in dates if d is not None), default=None)


def combine_sources(states: Iterable[WatchState]) -> WatchState:
    """Merge the Watch State of several Source Items paired with one Target Item."""
    states = list(states)
    return WatchState(
        played=any(s.played for s in states),
        last_played=_latest(*(s.last_played for s in states)),
        play_count=max(s.play_count for s in states),
        resume_ticks=max(s.resume_ticks for s in states),
    )


def merge(source: WatchState, target: WatchState, policy: ResumePolicy) -> WatchState:
    """Return the Watch State the Target Item should end up with."""
    match policy:
        case ResumePolicy.FURTHEST:
            resume_ticks = max(source.resume_ticks, target.resume_ticks)
        case ResumePolicy.SOURCE:
            resume_ticks = source.resume_ticks
        case ResumePolicy.SKIP:
            resume_ticks = target.resume_ticks

    return WatchState(
        played=source.played or target.played,
        last_played=_latest(source.last_played, target.last_played),
        play_count=max(source.play_count, target.play_count),
        resume_ticks=resume_ticks,
    )

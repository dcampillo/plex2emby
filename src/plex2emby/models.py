"""Domain types. Names follow GLOSSARY.md."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ResumePolicy(StrEnum):
    FURTHEST = "furthest"
    SOURCE = "source"
    SKIP = "skip"


class ItemKind(StrEnum):
    MOVIE = "movie"
    EPISODE = "episode"


@dataclass(frozen=True)
class WatchState:
    played: bool = False
    last_played: datetime | None = None
    play_count: int = 0
    resume_ticks: int = 0


@dataclass(frozen=True)
class SourceItem:
    """An Item on the Source Server. An episode carries its show's Provider IDs."""

    key: str
    title: str
    library: str
    kind: ItemKind
    watch_state: WatchState
    provider_ids: frozenset[str] = frozenset()
    filenames: frozenset[str] = frozenset()
    season: int | None = None
    episode: int | None = None


@dataclass(frozen=True)
class TargetItem:
    """An Item on the Target Server. An episode carries its show's Provider IDs."""

    id: str
    title: str
    kind: ItemKind
    watch_state: WatchState = field(default_factory=WatchState)
    provider_ids: frozenset[str] = frozenset()
    filename: str = ""
    season: int | None = None
    episode: int | None = None


@dataclass(frozen=True)
class Match:
    """One Target Item and every Source Item paired with it."""

    target: TargetItem
    sources: tuple[SourceItem, ...]


@dataclass(frozen=True)
class UnmatchedItem:
    source: SourceItem
    reason: str

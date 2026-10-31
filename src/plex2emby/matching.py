"""Pairs Source Items with Target Items. A wrong Match is worse than an Unmatched Item."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations

from plex2emby.models import ItemKind, Match, SourceItem, TargetItem, UnmatchedItem

NO_MATCH = "No Provider ID or filename match on Emby"
IDS_CONFLICT = "Provider IDs point to different Emby items"
FILENAME_CONFLICT = "Provider ID and filename point to different Emby items"
FILENAME_AMBIGUOUS = "Filename is shared by several Emby items"


@dataclass(frozen=True)
class MatchResult:
    matches: list[Match]
    unmatched: list[UnmatchedItem]


class _TargetIndex:
    def __init__(self, targets: Iterable[TargetItem]) -> None:
        self._by_id: dict[tuple, dict[str, TargetItem]] = defaultdict(dict)
        self._by_filename: dict[tuple, dict[str, TargetItem]] = defaultdict(dict)
        for target in targets:
            for provider_id in target.provider_ids:
                key = (target.kind, provider_id, target.season, target.episode)
                self._by_id[key][target.id] = target
            if target.filename:
                self._by_filename[(target.kind, target.filename.lower())][target.id] = target

    def by_provider_ids(self, source: SourceItem) -> list[dict[str, TargetItem]]:
        """One group of candidates per Provider ID that found anything."""
        if source.kind is ItemKind.EPISODE and (source.season is None or source.episode is None):
            return []
        keys = [(source.kind, p, source.season, source.episode) for p in source.provider_ids]
        return [self._by_id[key] for key in keys if key in self._by_id]

    def by_filenames(self, source: SourceItem) -> list[dict[str, TargetItem]]:
        keys = [(source.kind, name.lower()) for name in source.filenames]
        return [self._by_filename[key] for key in keys if key in self._by_filename]


def _resolve(source: SourceItem, index: _TargetIndex) -> list[TargetItem] | str:
    """Return the Target Items for a Source Item, or the reason there are none."""
    id_groups = index.by_provider_ids(source)
    if any(a.keys().isdisjoint(b.keys()) for a, b in combinations(id_groups, 2)):
        return IDS_CONFLICT

    file_groups = index.by_filenames(source)
    unique_files = {id: t for group in file_groups if len(group) == 1 for id, t in group.items()}

    if id_groups:
        by_id = {id: t for group in id_groups for id, t in group.items()}
        if unique_files and by_id.keys().isdisjoint(unique_files.keys()):
            return FILENAME_CONFLICT
        return list(by_id.values())

    if unique_files:
        return list(unique_files.values())
    return FILENAME_AMBIGUOUS if file_groups else NO_MATCH


def match_items(sources: Iterable[SourceItem], targets: Iterable[TargetItem]) -> MatchResult:
    index = _TargetIndex(targets)
    grouped: dict[str, tuple[TargetItem, list[SourceItem]]] = {}
    unmatched: list[UnmatchedItem] = []

    for source in sources:
        resolved = _resolve(source, index)
        if isinstance(resolved, str):
            unmatched.append(UnmatchedItem(source, resolved))
            continue
        for target in resolved:
            grouped.setdefault(target.id, (target, []))[1].append(source)

    matches = [Match(target, tuple(paired)) for target, paired in grouped.values()]
    return MatchResult(matches, unmatched)

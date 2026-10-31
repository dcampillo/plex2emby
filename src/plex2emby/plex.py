"""Read-only client for the Source Server."""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import PurePosixPath

import httpx

from plex2emby.models import ItemKind, SourceItem, WatchState

TICKS_PER_MILLISECOND = 10_000
PROVIDERS = ("imdb://", "tmdb://", "tvdb://")
MOVIE_TYPE = 1
SHOW_TYPE = 2
EPISODE_TYPE = 4


class UnknownLibrary(Exception):
    pass


def _provider_ids(row: dict) -> frozenset[str]:
    guids = (g["id"] for g in row.get("Guid") or [])
    return frozenset(g for g in guids if g.startswith(PROVIDERS))


def _filenames(row: dict) -> frozenset[str]:
    return frozenset(
        PurePosixPath(part["file"]).name
        for media in row.get("Media", [])
        for part in media.get("Part", [])
    )


def _watch_state(row: dict) -> WatchState:
    viewed_at = row.get("lastViewedAt")
    play_count = row.get("viewCount") or 0
    return WatchState(
        played=play_count > 0,
        last_played=datetime.fromtimestamp(viewed_at, UTC) if viewed_at else None,
        play_count=play_count,
        resume_ticks=(row.get("viewOffset") or 0) * TICKS_PER_MILLISECOND,
    )


def _has_history(row: dict) -> bool:
    return bool(row.get("viewCount") or row.get("viewOffset"))


class PlexClient:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def _get(self, path: str, **params) -> dict:
        response = self._http.get(path, params=params)
        response.raise_for_status()
        return response.json()["MediaContainer"]

    def libraries(self, names: Sequence[str] | None = None) -> list[dict]:
        """Movie and TV libraries, limited to `names` when given."""
        found = [
            d for d in self._get("/library/sections").get("Directory", [])
            if d["type"] in ("movie", "show")
        ]
        if not names:
            return found
        missing = set(names) - {d["title"] for d in found}
        if missing:
            raise UnknownLibrary(", ".join(sorted(missing)))
        return [d for d in found if d["title"] in names]

    def _rows(self, library: dict, item_type: int) -> list[dict]:
        path = f"/library/sections/{library['key']}/all"
        return self._get(path, type=item_type, includeGuids=1).get("Metadata", [])

    def _movies(self, library: dict) -> list[SourceItem]:
        return [
            SourceItem(
                key=row["ratingKey"],
                title=row["title"],
                library=library["title"],
                kind=ItemKind.MOVIE,
                watch_state=_watch_state(row),
                provider_ids=_provider_ids(row),
                filenames=_filenames(row),
            )
            for row in self._rows(library, MOVIE_TYPE)
            if _has_history(row)
        ]

    def _episodes(self, library: dict) -> list[SourceItem]:
        show_ids = {
            row["ratingKey"]: _provider_ids(row) for row in self._rows(library, SHOW_TYPE)
        }
        return [
            SourceItem(
                key=row["ratingKey"],
                title=f"{row.get('grandparentTitle')} - {row['title']}",
                library=library["title"],
                kind=ItemKind.EPISODE,
                watch_state=_watch_state(row),
                provider_ids=show_ids.get(row.get("grandparentRatingKey"), frozenset()),
                filenames=_filenames(row),
                season=row.get("parentIndex"),
                episode=row.get("index"),
            )
            for row in self._rows(library, EPISODE_TYPE)
            if _has_history(row)
        ]

    def source_items(self, libraries: list[dict]) -> list[SourceItem]:
        """Every Item with Watch State in the given libraries."""
        items: list[SourceItem] = []
        for library in libraries:
            read = self._movies if library["type"] == "movie" else self._episodes
            items.extend(read(library))
        return items

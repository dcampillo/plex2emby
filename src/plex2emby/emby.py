"""Client for the Target Server."""

from datetime import UTC, datetime
from pathlib import PurePosixPath

import httpx

from plex2emby.models import ItemKind, TargetItem, WatchState

PROVIDERS = ("imdb", "tmdb", "tvdb")


class UnknownUser(Exception):
    pass


def _provider_ids(row: dict) -> frozenset[str]:
    # Emby's key casing varies between items: both "Imdb" and "IMDB" occur.
    normalised = {key.lower(): value for key, value in (row.get("ProviderIds") or {}).items()}
    return frozenset(f"{p}://{normalised[p]}" for p in PROVIDERS if p in normalised)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(UTC).replace(microsecond=0)


def watch_state_from(user_data: dict) -> WatchState:
    return WatchState(
        played=bool(user_data.get("Played")),
        last_played=_parse_date(user_data.get("LastPlayedDate")),
        play_count=user_data.get("PlayCount") or 0,
        resume_ticks=user_data.get("PlaybackPositionTicks") or 0,
    )


def _with_watch_state(user_data: dict, state: WatchState) -> dict:
    """Overlay Watch State on a record, because Emby replaces the whole record on write."""
    updated = {
        **user_data,
        "Played": state.played,
        "PlayCount": state.play_count,
        "PlaybackPositionTicks": state.resume_ticks,
    }
    if state.last_played:
        updated["LastPlayedDate"] = state.last_played.strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
    return updated


class EmbyClient:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http
        self._user_id = ""

    def _get(self, path: str, **params) -> dict:
        response = self._http.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def log_in(self, user_name: str) -> None:
        users = self._get("/Users/Query")["Items"]
        ids = [u["Id"] for u in users if u["Name"] == user_name]
        if not ids:
            raise UnknownUser(user_name)
        self._user_id = ids[0]

    def target_items(self) -> list[TargetItem]:
        rows = self._get(
            f"/Users/{self._user_id}/Items",
            Recursive="true",
            IncludeItemTypes="Movie,Series,Episode",
            Fields="ProviderIds,Path",
        )["Items"]
        show_ids = {r["Id"]: _provider_ids(r) for r in rows if r["Type"] == "Series"}
        return [self._target_item(r, show_ids) for r in rows if r["Type"] != "Series"]

    def user_data(self, item_id: str) -> dict:
        return self._get(f"/Users/{self._user_id}/Items/{item_id}")["UserData"]

    def write_watch_state(self, item_id: str, user_data: dict, state: WatchState) -> None:
        response = self._http.post(
            f"/Users/{self._user_id}/Items/{item_id}/UserData",
            json=_with_watch_state(user_data, state),
        )
        response.raise_for_status()

    @staticmethod
    def _target_item(row: dict, show_ids: dict[str, frozenset[str]]) -> TargetItem:
        is_movie = row["Type"] == "Movie"
        return TargetItem(
            id=row["Id"],
            title=row["Name"],
            kind=ItemKind.MOVIE if is_movie else ItemKind.EPISODE,
            watch_state=watch_state_from(row.get("UserData") or {}),
            provider_ids=(
                _provider_ids(row) if is_movie else show_ids.get(row.get("SeriesId"), frozenset())
            ),
            filename=PurePosixPath(row.get("Path") or "").name,
            season=row.get("ParentIndexNumber"),
            episode=row.get("IndexNumber"),
        )

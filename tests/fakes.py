"""In-memory Plex and Emby servers. Response shapes are copied from real servers."""

import json

import httpx

PLEX_TOKEN = "plex-secret-token"
EMBY_KEY = "emby-secret-key"
USER_ID = "u1"


def plex_movie(key, title, *, guids=(), file=None, **state):
    return {
        "ratingKey": key,
        "type": "movie",
        "title": title,
        "Guid": [{"id": g} for g in guids] or None,
        "Media": [{"Part": [{"file": file or f"/plex/movies/{title}/{title}.mkv"}]}],
        **state,
    }


def plex_show(key, title, *, guids=()):
    return {"ratingKey": key, "type": "show", "title": title, "Guid": [{"id": g} for g in guids]}


def plex_episode(key, title, *, show, season, number, file=None, **state):
    return {
        "ratingKey": key,
        "type": "episode",
        "title": title,
        "grandparentRatingKey": show,
        "grandparentTitle": "Show",
        "parentIndex": season,
        "index": number,
        "Guid": [{"id": f"tvdb://ep{key}"}],
        "Media": [{"Part": [{"file": file or f"/plex/tv/{title}.mkv"}]}],
        **state,
    }


class FakePlex:
    def __init__(self):
        self.sections = {}

    def add_section(self, key, title, section_type, *, items=(), shows=()):
        self.sections[key] = {
            "title": title,
            "type": section_type,
            "items": list(items),
            "shows": list(shows),
        }

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("X-Plex-Token") != PLEX_TOKEN:
            return httpx.Response(401)
        path = request.url.path
        if path == "/library/sections":
            directories = [
                {"key": key, "type": s["type"], "title": s["title"]}
                for key, s in self.sections.items()
            ]
            return self._container({"Directory": directories})

        key = path.split("/")[3]
        section = self.sections[key]
        rows = section["shows"] if request.url.params["type"] == "2" else section["items"]
        if request.url.params.get("includeGuids") != "1":
            rows = [{k: v for k, v in row.items() if k != "Guid"} for row in rows]
        return self._container({"Metadata": rows})

    @staticmethod
    def _container(body):
        return httpx.Response(200, json={"MediaContainer": body})


def emby_item(item_id, name, item_type, *, path, ids=None, user_data=None, **extra):
    data = {"PlaybackPositionTicks": 0, "PlayCount": 0, "IsFavorite": False, "Played": False}
    return {
        "Id": item_id,
        "Name": name,
        "Type": item_type,
        "Path": path,
        "ProviderIds": ids or {},
        "UserData": {**data, **(user_data or {})},
        **extra,
    }


class FakeEmby:
    def __init__(self):
        self.items = {}
        self.writes = []
        self.reject_writes_for = set()
        self.ignore_writes_for = set()

    def add(self, *items):
        for item in items:
            self.items[item["Id"]] = item

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("X-Emby-Token") != EMBY_KEY:
            return httpx.Response(401)
        path = request.url.path
        if path == "/Users/Query":
            return httpx.Response(200, json={"Items": [{"Name": "test-user", "Id": USER_ID}]})
        if path == f"/Users/{USER_ID}/Items":
            wanted = request.url.params["IncludeItemTypes"].split(",")
            items = [i for i in self.items.values() if i["Type"] in wanted]
            return httpx.Response(200, json={"Items": items, "TotalRecordCount": len(items)})

        item_id = path.split("/")[4]
        if request.method == "GET":
            return httpx.Response(200, json=self.items[item_id])
        return self._write(item_id, json.loads(request.content))

    def _write(self, item_id, body):
        self.writes.append(item_id)
        if item_id in self.reject_writes_for:
            return httpx.Response(500)
        if item_id not in self.ignore_writes_for:
            self.items[item_id]["UserData"] = body  # Emby replaces the whole record.
        return httpx.Response(204)

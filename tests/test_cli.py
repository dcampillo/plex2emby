import csv
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from plex2emby import cli
from tests.fakes import (
    EMBY_KEY,
    PLEX_TOKEN,
    FakeEmby,
    FakePlex,
    emby_item,
    plex_episode,
    plex_movie,
    plex_show,
)

PLEX_URL = "https://plex.test"
EMBY_URL = "https://emby.test"
WATCHED_AT = 1600000000  # 2020-09-13T12:26:40Z


@pytest.fixture
def plex():
    return FakePlex()


@pytest.fixture
def emby():
    return FakeEmby()


@pytest.fixture(autouse=True)
def environment(monkeypatch, tmp_path, plex, emby):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PLEX_URL", PLEX_URL)
    monkeypatch.setenv("PLEX_TOKEN", PLEX_TOKEN)
    monkeypatch.setenv("EMBY_URL", EMBY_URL)
    monkeypatch.setenv("EMBY_API_KEY", EMBY_KEY)
    monkeypatch.setenv("EMBY_USER", "test-user")

    def fake_client(base_url, headers):
        handler = plex.handle if base_url == PLEX_URL else emby.handle
        return httpx.Client(
            base_url=base_url, headers=headers, transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(cli, "make_http_client", fake_client)


def run(*args):
    return CliRunner().invoke(cli.app, ["migrate", *args])


def report_rows():
    reports = list(Path("reports").glob("*.csv"))
    assert len(reports) == 1
    with reports[0].open(newline="") as f:
        return list(csv.DictReader(f))


def add_sample_film(plex, emby):
    plex.add_section(
        "1",
        "Movies",
        "movie",
        items=[
            plex_movie(
                "101",
                "Sample Film",
                guids=["imdb://tt0000001", "tmdb://1001"],
                viewCount=2,
                lastViewedAt=WATCHED_AT,
                viewOffset=60_000,
            )
        ],
    )
    emby.add(
        emby_item(
            "201",
            "Sample Film",
            "Movie",
            path="/emby/movies/Sample Film/Sample Film.mkv",
            ids={"Imdb": "tt0000001", "Tmdb": "1001"},
            user_data={"IsFavorite": True},
        )
    )


def test_dry_run_reports_the_change_and_writes_nothing(plex, emby):
    add_sample_film(plex, emby)

    result = run()

    assert result.exit_code == 0, result.output
    assert emby.writes == []
    row = report_rows()[0]
    assert row["status"] == "would-change"
    assert row["title"] == "Sample Film"
    assert row["old_played"] == "False"
    assert row["new_played"] == "True"
    assert row["new_play_count"] == "2"
    assert row["new_last_played"] == "2020-09-13T12:26:40+00:00"
    assert row["new_resume_ticks"] == "600000000"  # one minute


def test_episode_matches_through_its_shows_provider_id(plex, emby):
    plex.add_section(
        "2",
        "TV Series",
        "show",
        shows=[plex_show("301", "Sample Show", guids=["tvdb://2001"])],
        items=[
            plex_episode(
                "302",
                "Pilot",
                show="301",
                season=8,
                number=1,
                viewCount=1,
                lastViewedAt=WATCHED_AT,
            )
        ],
    )
    emby.add(
        emby_item("401", "Sample Show", "Series", path="/emby/tv/Sample Show", ids={"IMDB": "tt0000002", "Tvdb": "2001"}),
        emby_item(
            "402",
            "Pilot",
            "Episode",
            path="/emby/tv/Sample Show/S08E01.mkv",
            SeriesId="401",
            ParentIndexNumber=8,
            IndexNumber=1,
        ),
    )

    assert run().exit_code == 0
    assert report_rows()[0]["emby_id"] == "402"


def test_video_with_no_provider_ids_matches_by_filename_across_mount_paths(plex, emby):
    plex.add_section(
        "11",
        "Home Videos",
        "movie",
        items=[
            plex_movie(
                "501", "Holiday Clip", file="/plex/home/Holiday Clip.mov", viewOffset=120000
            )
        ],
    )
    emby.add(emby_item("9", "Holiday Clip", "Movie", path="/emby/home/Holiday Clip.mov"))

    assert run().exit_code == 0
    row = report_rows()[0]
    assert (row["status"], row["emby_id"]) == ("would-change", "9")
    assert row["new_played"] == "False"


def test_unmatched_item_is_reported_without_failing_the_run(plex, emby):
    add_sample_film(plex, emby)
    plex.sections["1"]["items"].append(
        plex_movie("2", "Home Video", viewCount=1, lastViewedAt=WATCHED_AT)
    )

    assert run().exit_code == 0
    unmatched = [r for r in report_rows() if r["status"] == "unmatched"]
    assert [r["title"] for r in unmatched] == ["Home Video"]
    assert unmatched[0]["reason"]
    assert unmatched[0]["library"] == "Movies"


def test_item_with_no_history_is_ignored(plex, emby):
    plex.add_section("1", "Movies", "movie", items=[plex_movie("1", "Unseen")])

    assert run().exit_code == 0
    assert report_rows() == []


def test_music_and_photo_libraries_are_skipped(plex, emby):
    add_sample_film(plex, emby)
    plex.add_section("9", "Music", "artist", items=[{"will": "crash if read"}])

    assert run().exit_code == 0


def test_library_option_limits_the_run(plex, emby):
    add_sample_film(plex, emby)
    plex.add_section("11", "Home Videos", "movie", items=[plex_movie("2", "Clip", viewCount=1)])

    assert run("--library", "Home Videos").exit_code == 0
    assert [r["title"] for r in report_rows()] == ["Clip"]


def test_unknown_library_stops_before_any_report(plex, emby):
    add_sample_film(plex, emby)

    result = run("--library", "Nope")

    assert result.exit_code != 0
    assert "Nope" in result.output
    assert not Path("reports").exists()


def test_bad_emby_key_fails_cleanly_without_leaking_secrets(plex, emby, monkeypatch):
    add_sample_film(plex, emby)
    monkeypatch.setenv("EMBY_API_KEY", "wrong-key")

    result = run()

    assert result.exit_code != 0
    assert "Emby" in result.output
    assert "wrong-key" not in result.output
    assert PLEX_TOKEN not in result.output


def test_unknown_emby_user_fails_cleanly(plex, emby, monkeypatch):
    add_sample_film(plex, emby)
    monkeypatch.setenv("EMBY_USER", "nobody")

    result = run()

    assert result.exit_code != 0
    assert "nobody" in result.output


def test_missing_setting_is_named(monkeypatch):
    monkeypatch.delenv("PLEX_TOKEN")

    result = run()

    assert result.exit_code != 0
    assert "PLEX_TOKEN" in result.output


def add_two_movies(plex, emby):
    plex.add_section(
        "1",
        "Movies",
        "movie",
        items=[
            plex_movie("1", "First", guids=["imdb://tt1"], viewCount=1, lastViewedAt=WATCHED_AT),
            plex_movie("2", "Second", guids=["imdb://tt2"], viewCount=1, lastViewedAt=WATCHED_AT),
        ],
    )
    emby.add(
        emby_item("a", "First", "Movie", path="/m/First.mkv", ids={"Imdb": "tt1"}),
        emby_item("b", "Second", "Movie", path="/m/Second.mkv", ids={"Imdb": "tt2"}),
    )


def test_apply_writes_watch_state_and_keeps_other_user_data(plex, emby):
    add_sample_film(plex, emby)

    result = run("--apply")

    assert result.exit_code == 0, result.output
    data = emby.items["201"]["UserData"]
    assert data["Played"] is True
    assert data["PlayCount"] == 2
    assert data["PlaybackPositionTicks"] == 600_000_000
    assert data["LastPlayedDate"].startswith("2020-09-13T12:26:40")
    assert data["IsFavorite"] is True
    assert report_rows()[0]["status"] == "changed"


def test_second_apply_writes_nothing(plex, emby):
    add_sample_film(plex, emby)

    run("--apply")
    emby.writes.clear()
    result = run("--apply")

    assert result.exit_code == 0
    assert emby.writes == []


def test_later_emby_date_in_emby_format_is_kept(plex, emby):
    add_sample_film(plex, emby)
    emby.items["201"]["UserData"]["LastPlayedDate"] = "2026-05-03T10:00:00.0000000Z"

    assert run("--apply").exit_code == 0
    assert emby.items["201"]["UserData"]["LastPlayedDate"].startswith("2026-05-03T10:00:00")


def test_rejected_write_is_reported_and_the_run_continues(plex, emby):
    add_two_movies(plex, emby)
    emby.reject_writes_for.add("a")

    result = run("--apply")

    assert result.exit_code == 1
    assert emby.items["b"]["UserData"]["Played"] is True
    statuses = {r["emby_id"]: r["status"] for r in report_rows()}
    assert statuses == {"a": "failed", "b": "changed"}


def test_write_that_does_not_stick_is_a_failure(plex, emby):
    add_two_movies(plex, emby)
    emby.ignore_writes_for.add("a")

    result = run("--apply")

    assert result.exit_code == 1
    failed = [r for r in report_rows() if r["status"] == "failed"]
    assert [r["emby_id"] for r in failed] == ["a"]
    assert "read-back" in failed[0]["reason"].lower()


def test_failed_item_is_retried_by_the_next_run(plex, emby):
    add_two_movies(plex, emby)
    emby.reject_writes_for.add("a")
    run("--apply")
    emby.reject_writes_for.clear()
    emby.writes.clear()

    assert run("--apply").exit_code == 0
    assert emby.writes == ["a"]


def test_default_policy_never_lowers_a_resume_position(plex, emby):
    add_sample_film(plex, emby)
    emby.items["201"]["UserData"]["PlaybackPositionTicks"] = 900_000_000

    assert run("--apply").exit_code == 0
    assert emby.items["201"]["UserData"]["PlaybackPositionTicks"] == 900_000_000


def test_source_policy_lowers_a_resume_position_on_request(plex, emby):
    add_sample_film(plex, emby)
    emby.items["201"]["UserData"]["PlaybackPositionTicks"] = 900_000_000

    assert run("--apply", "--resume-position", "source").exit_code == 0
    assert emby.items["201"]["UserData"]["PlaybackPositionTicks"] == 600_000_000


def test_skip_policy_leaves_resume_positions_alone(plex, emby):
    add_sample_film(plex, emby)

    assert run("--apply", "--resume-position", "skip").exit_code == 0
    assert emby.items["201"]["UserData"]["PlaybackPositionTicks"] == 0
    assert emby.items["201"]["UserData"]["Played"] is True

from plex2emby.matching import match_items
from plex2emby.models import ItemKind, SourceItem, TargetItem, WatchState

PLAYED = WatchState(played=True, play_count=1)


def movie(key="p1", ids=(), filenames=()):
    return SourceItem(
        key=key,
        title=key,
        library="Movies",
        kind=ItemKind.MOVIE,
        watch_state=PLAYED,
        provider_ids=frozenset(ids),
        filenames=frozenset(filenames),
    )


def episode(key="p1", ids=(), season=1, number=1, filenames=()):
    return SourceItem(
        key=key,
        title=key,
        library="TV Series",
        kind=ItemKind.EPISODE,
        watch_state=PLAYED,
        provider_ids=frozenset(ids),
        filenames=frozenset(filenames),
        season=season,
        episode=number,
    )


def emby_movie(id="e1", ids=(), filename=""):
    return TargetItem(
        id=id, title=id, kind=ItemKind.MOVIE, provider_ids=frozenset(ids), filename=filename
    )


def emby_episode(id="e1", ids=(), season=1, number=1, filename=""):
    return TargetItem(
        id=id,
        title=id,
        kind=ItemKind.EPISODE,
        provider_ids=frozenset(ids),
        filename=filename,
        season=season,
        episode=number,
    )


def matched(result):
    return {m.target.id: {s.key for s in m.sources} for m in result.matches}


def unmatched(result):
    return {u.source.key: u.reason for u in result.unmatched}


def test_movie_matches_on_any_shared_provider_id():
    result = match_items(
        [movie(ids=["tmdb://1001"])],
        [emby_movie(ids=["imdb://tt0000001", "tmdb://1001"])],
    )

    assert matched(result) == {"e1": {"p1"}}


def test_movie_ids_do_not_match_a_same_numbered_episode():
    result = match_items(
        [movie(ids=["tvdb://5"])],
        [emby_episode(ids=["tvdb://5"])],
    )

    assert matched(result) == {}
    assert "p1" in unmatched(result)


def test_episode_matches_on_show_id_plus_season_and_number():
    result = match_items(
        [episode(ids=["tvdb://2001"], season=8, number=1)],
        [
            emby_episode("wrong", ids=["tvdb://2001"], season=8, number=2),
            emby_episode("right", ids=["tvdb://2001"], season=8, number=1),
        ],
    )

    assert matched(result) == {"right": {"p1"}}


def test_provider_ids_pointing_at_different_items_is_unmatched():
    result = match_items(
        [episode(ids=["imdb://uk", "tvdb://us"])],
        [
            emby_episode("uk", ids=["imdb://uk"]),
            emby_episode("us", ids=["tvdb://us"]),
        ],
    )

    assert matched(result) == {}
    assert "provider" in unmatched(result)["p1"].lower()


def test_show_id_and_filename_disagreeing_is_unmatched():
    result = match_items(
        [episode(ids=["tvdb://1"], filenames=["show.s01e01.mkv"])],
        [
            emby_episode("by-id", ids=["tvdb://1"], filename="other.mkv"),
            emby_episode("by-file", ids=[], season=2, number=9, filename="show.s01e01.mkv"),
        ],
    )

    assert matched(result) == {}
    assert "filename" in unmatched(result)["p1"].lower()


def test_filename_fallback_ignores_case():
    result = match_items(
        [movie(filenames=["Holiday Clip.MOV"])],
        [emby_movie(filename="holiday clip.mov")],
    )

    assert matched(result) == {"e1": {"p1"}}


def test_filename_shared_by_two_emby_items_is_unmatched():
    result = match_items(
        [movie(filenames=["movie.mkv"])],
        [emby_movie("a", filename="movie.mkv"), emby_movie("b", filename="movie.mkv")],
    )

    assert matched(result) == {}
    assert "filename" in unmatched(result)["p1"].lower()


def test_same_title_is_never_enough():
    source = SourceItem(
        key="p1", title="Dune", library="Movies", kind=ItemKind.MOVIE, watch_state=PLAYED
    )

    result = match_items([source], [TargetItem(id="e1", title="Dune", kind=ItemKind.MOVIE)])

    assert matched(result) == {}
    assert "p1" in unmatched(result)


def test_one_plex_item_updates_every_emby_copy():
    result = match_items(
        [movie(ids=["imdb://tt1"])],
        [emby_movie("hd", ids=["imdb://tt1"]), emby_movie("uhd", ids=["imdb://tt1"])],
    )

    assert matched(result) == {"hd": {"p1"}, "uhd": {"p1"}}


def test_two_plex_items_group_under_one_emby_item():
    result = match_items(
        [movie("a", ids=["imdb://tt1"]), movie("b", ids=["imdb://tt1"])],
        [emby_movie(ids=["imdb://tt1"])],
    )

    assert matched(result) == {"e1": {"a", "b"}}


def test_ids_seeing_overlapping_copies_is_not_a_conflict():
    result = match_items(
        [movie(ids=["imdb://tt1", "tmdb://1"])],
        [
            emby_movie("hd", ids=["imdb://tt1", "tmdb://1"]),
            emby_movie("uhd", ids=["imdb://tt1"]),
        ],
    )

    assert matched(result) == {"hd": {"p1"}, "uhd": {"p1"}}


def test_item_with_no_candidate_is_unmatched():
    result = match_items([movie(ids=["imdb://tt1"])], [])

    assert "p1" in unmatched(result)

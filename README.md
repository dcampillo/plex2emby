# plex2emby

Copies your viewing history from Plex to Emby: played status, last-played date, play count and resume position, for movies and TV episodes. It's a one-off tool you can safely run again, not a continuous sync. Plex is never changed.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```sh
cp .env.sample .env   # then fill in your servers and keys
uv sync
```

## Usage

Every run is a Dry Run unless you add `--apply`:

```sh
uv run plex2emby migrate                     # show what would change
uv run plex2emby migrate --library Movies    # limit to a library (repeatable)
uv run plex2emby migrate --apply             # write to Emby
```

Back up Emby before your first `--apply`. There's no undo command, but each run's report in `reports/` lists the old and new values of everything it changed.

| `--resume-position` | When the two servers differ |
| --- | --- |
| `furthest` (default) | The larger position wins |
| `source` | Plex's position wins, even if that lowers Emby's |
| `skip` | Emby's position is left alone |

## How it behaves

- **Additive:** played stays played, the latest date and highest play count win, and no dates are invented. `--resume-position source` is the only option that can lower anything.
- **Matching:** movies match on any shared IMDb, TMDb or TVDb ID. Episodes match on the show's ID plus season and episode number. The fallback is the filename, only if exactly one Emby item has it.
- **No guessing:** if the evidence conflicts, or nothing matches, the item is reported as unmatched rather than migrated. Titles are never used for matching.
- **Verified writes:** every write is read back. A failed item is reported, the run continues, and the next run retries it.

Exit codes: `0` no failed writes (unmatched items are fine), `1` at least one write failed, `2` the run couldn't start.

## Development

```sh
uv run pytest
```

Domain terms are defined in `GLOSSARY.md`.

"""One Migration Run: match, merge, and either report or apply each change."""

import httpx

from plex2emby.emby import EmbyClient, watch_state_from
from plex2emby.matching import match_items
from plex2emby.merge import combine_sources, merge
from plex2emby.models import Match, ResumePolicy, SourceItem, TargetItem
from plex2emby.report import CHANGED, FAILED, UNMATCHED, WOULD_CHANGE, ReportRow


def _plan(match: Match, policy: ResumePolicy) -> ReportRow | None:
    """What this Match would change, or None if the Target Item is already up to date."""
    source_state = combine_sources(s.watch_state for s in match.sources)
    current = match.target.watch_state
    desired = merge(source_state, current, policy)
    if desired == current:
        return None
    return ReportRow(
        status=WOULD_CHANGE,
        library=match.sources[0].library,
        title=match.target.title,
        emby_id=match.target.id,
        old=current,
        new=desired,
    )


def _apply(emby: EmbyClient, match: Match, policy: ResumePolicy) -> ReportRow | None:
    """Read, merge, post, and read back, so a success is a confirmed success."""
    source_state = combine_sources(s.watch_state for s in match.sources)
    row = dict(
        library=match.sources[0].library, title=match.target.title, emby_id=match.target.id
    )
    current = desired = None
    try:
        user_data = emby.user_data(match.target.id)
        current = watch_state_from(user_data)
        desired = merge(source_state, current, policy)
        if desired == current:
            return None
        emby.write_watch_state(match.target.id, user_data, desired)
        confirmed = watch_state_from(emby.user_data(match.target.id))
    except httpx.HTTPError as error:
        return ReportRow(FAILED, old=current, new=desired, reason=str(error), **row)

    if confirmed != desired:
        reason = "Read-back did not show the written Watch State"
        return ReportRow(FAILED, old=current, new=desired, reason=reason, **row)
    return ReportRow(CHANGED, old=current, new=desired, **row)


def run_migration(
    sources: list[SourceItem],
    targets: list[TargetItem],
    policy: ResumePolicy,
    emby: EmbyClient,
    apply: bool,
) -> list[ReportRow]:
    result = match_items(sources, targets)
    rows = [
        row
        for match in result.matches
        if (row := _apply(emby, match, policy) if apply else _plan(match, policy))
    ]
    rows += [
        ReportRow(UNMATCHED, u.source.library, u.source.title, reason=u.reason)
        for u in result.unmatched
    ]
    return rows

# plex2emby

Carries one person's viewing history from their Plex server to their Emby server during a changeover.

## Language

**Source Server**:
The Plex server that viewing history is read from. It is never changed.
_Avoid_: Origin, from-server

**Target Server**:
The Emby server that viewing history is written to.
_Avoid_: Destination, to-server

**Item**:
A single movie or TV episode. Shows, seasons, music and photos are not Items.
_Avoid_: Media, title, video

**Watch State**:
Everything one user's history records about one Item: played or not, last-played date, play count, and resume position.
_Avoid_: Watched status, watch history, progress

**Provider ID**:
An identifier from an external catalogue (IMDb, TMDb or TVDb) that names the same movie or show on both servers.
_Avoid_: GUID, external ID, metadata ID

**Match**:
The pairing of an Item on the Source Server with the same Item on the Target Server.
_Avoid_: Mapping, link

**Unmatched Item**:
An Item on the Source Server with Watch State but no Match, so it is reported rather than migrated.
_Avoid_: Missing item, orphan

**Migration Run**:
One execution of the tool. It can be repeated safely and only ever adds to the Watch State on the Target Server, except where a Resume Policy of Source says otherwise.
_Avoid_: Sync, import

**Resume Policy**:
The rule for settling a resume position when the two servers differ: Furthest (the larger position wins), Source (the Source Server's position wins, even if that lowers it), or Skip (the Target Server's position is left alone).
_Avoid_: Conflict mode, resume strategy

**Dry Run**:
A Migration Run that reports what would change without writing to the Target Server. This is the default.
_Avoid_: Preview, simulation

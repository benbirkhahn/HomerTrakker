# Offline Event-Matching Validation

## Result

An isolated, synthetic offline test run passed **7 of 7 tests** on 2026-10-29. The checks exercised stable event identity, broadcast clip binding, reviewed-animation validation, retry-state idempotency, missing-data rejection, and the publication guard. No production code was changed as part of that test run.

## Findings

- A home-run event is identified by `gamePk:atBatIndex:batterId:hitPlayId`. Two events by the same batter therefore remain distinct when their hit play IDs differ.
- Statcast enrichment resolves a post against event identity and records the event key, hit play ID, and selected play’s statistics.
- Broadcast content matching uses the content GUID as the hit play ID and rejects ambiguous event or clip ownership.
- Animation matching checks the reviewed evidence and its observed event details against the current game feed. The synthetic wrong-play and missing-stat tests were rejected.
- Retry state is keyed by event identity; remembering an existing event preserves its prior retry status rather than creating another event.
- A missing animation does not get fabricated by matching. A broadcast clip may still resolve independently.

## Safety and scope

The harness used invented event data and synthetic media/frame bytes, an isolated HOME and temporary state, and blocked `urllib.request.urlopen`, `socket.create_connection`, and direct socket connections. It did not run pollers, uploaders, queue optimizers, cleanup, notifications, or production entry points.

The publication-guard test verified the guard function in isolation. It did **not** test integration with the uploader or notification implementations. No network/API, real media, or scheduled/private publishing behavior was tested; private or scheduled uploads remain publishing and were not attempted. The offline results do not establish end-to-end production safety.

## Reproducibility

The standalone test harness and detailed run record were kept outside the repository at `/Users/benbirkhahn/Documents/Codex/2026-10-28/task-2/warp-results/homertrakker/`. The handoff there records the exact command, source snapshot, individual test cases, and skipped checks. The harness is not bundled with this repository and its machine-specific command should not be treated as a project test target.

## Source reviewed

`homer_event_identity.py`, `statcast_enricher.py`, `homer_clip_matcher.py`, `animation_manifest.py`, `pending_homers.py`, and `publication_guard.py` were reviewed for the event path. The enrichment module was reviewed statically; its network-capable entry point was not executed.

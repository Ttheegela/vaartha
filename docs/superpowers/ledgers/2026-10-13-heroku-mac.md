# SDD ledger — plan: docs/superpowers/plans/2026-10-13-heroku-mac.md
Spec: docs/superpowers/specs/2026-10-11-varta-v2-design.md §2/§4/§7. Branch start 933da75.

## Pre-flight scan
| Pair / task | Produces vs consumes | Finding |
|---|---|---|
| T1→T2 | CORS_ORIGINS + credentials; cookie domain → web fetches with credentials: include | consistent |
| T1→T3 | env RUN_WORKER/CORS_ORIGINS/COOKIE_DOMAIN/PORT used in heroku.md config vars | consistent |
| T1→T4 | owner.sh sets RUN_WORKER=1, unsets CORS/COOKIE/TRUST_PROXY | consistent |
| T2→T3 | NEXT_PUBLIC_API_BASE build arg in web/Dockerfile ↔ workflow --build-arg | consistent |
| T3→T5 / T4→T5 | doc paths deploy/heroku.md, deploy/owner-mac.md | consistent |
| T1 self | boot reseed records job timestamps so tick doesn't repeat | consistent (plan edited) |
| T2 self | server-side apiGet unchanged | consistent |
| T4 self | check mode testable without starting servers | consistent |
| T6 | controller with Tarun | not dispatched |
Task 1: dispatched sonnet ac60293d3dae0abc4, commit 45bfbec; DONE_WITH_CONCERNS (no RED; Dockerfile sh -c untested)
Task 1: ⚠️ carried — allow_headers content-type only → Task 2 fetches must send no other custom headers; cookie only works with shared custom domain (herokuapp.com is PSL) → Task 3 runbook must say so
Task 1: minor (deferred): boot-reseed skip test time-of-day dependent (at-jobs before 03:00/07:00); shutdown join path untested; worker thread death before loop not logged; boot_reseed_if_empty uses datetime.now not injectable clock
Task 1: complete (commits 933da75..45bfbec, review clean)
Task 2: dispatched sonnet a97a7fa3bc8b0f114, commit 65648b9
Task 2: ⚠️ resolved — no zzapi value left in web/.next (controller grep); build-arg in workflow → Task 3
Task 2: minor (deferred): apiUrl default env path not unit-tested (verified by build inlining)
Task 2: complete (commits 45bfbec..65648b9, review clean)
Task 3: dispatched sonnet a118964be48ac2da6, commit c93aae1 (Accept version=3.docker-releases per Heroku docs)
Task 3: review — 1 Important (config:set echoes secrets) + minors → fix round 1 sent
Task 3: fix round 1/5 (4 addressed, 1 open — R14 guidance Standard-1X wrong (controller's instruction error); new minor: web ps:type missing; commits c93aae1..b468b95) → round 2 sent
Task 3: fix round 2/5 (2 addressed, 0 open — Standard-2X guidance with cost, web ps:type; commits b468b95..d378d08)
Task 3: minor (deferred): stderr of config:set not redirected (key names only); PLAID_SECRET in argv briefly visible to local ps (documented)
Task 3: complete (commits 65648b9..d378d08, review clean)
Task 4: dispatched sonnet a2b04b43422a30d4f, commit 5c25879
Task 4: review (opus) — 1 Critical (launchd kills process group), 4 Important (plist PATH lacks uv; stale/demo web build reused; pidfile is uv not uvicorn; unquoted env passes check but breaks start) + minors → fix round 1 sent
Task 4: fix round 1/5 (6 addressed, 0 open — AbandonProcessGroup, PATH, build stamp, venv uvicorn, env validation, minors; commits 5c25879..280528b)
Task 4: minor (deferred): start/stop/launchd not run live (verify in Task 6 with Tarun); web/public changes not refreshed (dir doesn't exist)
Task 4: complete (commits d378d08..280528b, review clean)
Task 5: dispatched haiku a7cc2d7210824f042, commit 0fdfece
Task 5: Ruling: docs-only 14-line diff reviewed by controller read-through instead of a separate reviewer seat; final opus review covers it — cost if wrong: a doc inaccuracy caught later
Task 5: complete (commits 280528b..0fdfece)
Final review (opus a0401e6db4e205478): 0 Critical, 1 Important (owner.sh trusts recycled pids), 9 Minor. Fix wave: I1 + minors 1-8.
Final: Ruling: skip minor 9 (500s lack CORS headers) — UI treats both as unavailable — cost if wrong: harder debugging in browser console
Final: fixed I1 + minors 2-7 (commits 0fdfece..ea9bcd8); re-review all addressed (classifier unavailable during re-review — controller verified: tree clean, no stray processes, 290 passed, ruff clean)
Final: minor (deferred): alive() marker is substring match; owner start/stop/launchd still unverified live (Task 6)

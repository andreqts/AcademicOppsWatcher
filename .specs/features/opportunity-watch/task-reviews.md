> **Analysis of item 1 (Claude, 2026-09-22) - Partly grounded; not a blocker for Claude Code.**
> The skill exists at `.claude/skills/tlc-spec-driven/` and is in Claude Code's skill list for this repo. Copies also exist at `.cursor/skills/tlc-spec-driven/` and `.windsurf/skills/tlc-spec-driven/`. `.agents/` is empty, so a tool that loads skills from `.agents/skills/` (e.g. Codex) cannot see it, which is probably where this review came from. In that tool the "stop if the skill cannot be activated" rule applies as written.
> **Proposed fix:** run Execute with Claude Code, Cursor or Windsurf. Or, if another tool must run it, copy the skill into `.agents/skills/tlc-spec-driven/` first. No change to `tasks.md` needed.
> **Applied 2026-09-22:** copied the skill to `.agents/skills/tlc-spec-driven/` (identical to `.claude/skills/`, checked with `diff -rq`). `.agents/.skill-lock.json` was not edited; re-run the skill installer with that agent if you want the lock to list it.

1. Blocker: required execution skill is unavailable.
The file mandates activating tlc-spec-driven, and says to stop if it cannot be activated. That skill is not present in the available skill list, so execution cannot follow the documented protocol. See tasks.md.

> **Analysis of item 2 (Claude, 2026-09-22) - Grounded.**
> `design.md:158-159` declares both `notify` functions as `-> NotifyResult`, but the Data Models section never defines `NotifyResult`, and T2's model list omits it. T15 (`tasks.md:441`) also says a send error becomes a `FailureRecord(type="email")` without saying how it reaches the caller. The orchestrator (T17) needs that record for P2b-AC1.
> **Proposed fix:** add to `design.md` Data Models and to T2: `NotifyResult(sent_to: int, skipped: bool, failure: FailureRecord | None)`. `sent_to` is a count, never addresses (AD-001). T15 returns the failure inside `NotifyResult`; `run.main` appends it to the run's failures.
> **Applied 2026-09-22:** `NotifyResult` added to `design.md` Data Models plus a notify **Returns** line; T2 and T15 updated.

2. High: notification API/data model is undefined.
T15 requires NotifyResult, but design.md and T2’s required model list do not define it. Also, T15 says send errors become FailureRecords, while the design signatures only return NotifyResult. The return shape and failure propagation need to be specified consistently.

> **Analysis of item 3 (Claude, 2026-09-22) - Grounded.**
> `design.md:136` says `classify(candidate) -> ValidationResult`; T12 says it returns "a ValidationResult plus any FailureRecords". The two contradict each other. The degraded case (Jev fails, fallback succeeds, P1-AC19) needs a failure record *and* a verdict, and `ValidationResult` alone cannot carry both.
> **Proposed fix:** change the design signature to `classify(candidate) -> tuple[ValidationResult, list[FailureRecord]]`, the same shape `search.run_searches` already uses. T12 unchanged apart from citing the signature.
> **Applied 2026-09-22:** `design.md` `classify` signature now returns `tuple[ValidationResult, list[FailureRecord]]`; T12 cites it.

3. High: classify has conflicting signatures.
T12 says it returns a ValidationResult plus failure records, while design.md declares classify(candidate) -> ValidationResult. This affects orchestrator integration and tests.

> **Analysis of item 4 (Claude, 2026-09-22) - Grounded.**
> `SeenStore.apply_run(candidates: list[Candidate], ...)` implies full `Candidate` objects (with `verdict`), but already-seen results come back from search only as `RawResult`s. The diagram sends "already-seen ids" to `apply_run`, yet no task says how they are turned into input, so an implementer could rebuild a `Candidate` with a wrong or default verdict and overwrite a stored `false_positive`.
> **Proposed fix:** change the interface to `apply_run(found_ids: set[str], new_candidates: list[Candidate], today, count_misses)`. `found_ids` holds every id seen in this run's search results, new or not; `apply_run` sets `last_seen`/`miss_count` for them from the store and never touches a stored `verdict`. `new_candidates` holds only the freshly classified entries to insert. Update `design.md` (state interface), T7 (add a test that a found already-seen `false_positive` keeps its verdict) and T17 (build `found_ids` from all deduped results).
> **Applied 2026-09-22:** `apply_run(found_ids, new_candidates, today, count_misses)` in `design.md`; T7 gained the verdict-preservation test; T17 builds `found_ids`.

4. High: existing candidates are not clearly passed through state updates.
Only unseen candidates are classified, but apply_run must update last_seen, reset reappearing miss_count, and preserve existing verdicts. T17 does not specify how already-seen search results are reconstructed as Candidate objects and supplied to apply_run.

> **Analysis of item 5 (Claude, 2026-09-22) - Grounded (small).**
> With `python -m opportunity_watch.run`, a plain `main()` call discards the returned exit code, so a handled failure could still exit 0. The re-raise path does exit non-zero on its own (an uncaught exception exits 1), but the returned-code path does not.
> **Proposed fix:** add to T17's "What": `if __name__ == "__main__": raise SystemExit(main())`, plus one integration test that runs the module in a subprocess and asserts the exit code.
> **Applied 2026-09-22:** T17 requires `raise SystemExit(main())` and a subprocess exit-code test.

5. Medium: module entry-point behavior is underspecified.
T17 requires main() -> int, but also requires re-raising unexpected exceptions and running via python -m opportunity_watch.run. It should explicitly require a module guard such as raise SystemExit(main()); otherwise the returned exit code may be ignored.

> **Analysis of item 6 (Claude, 2026-09-22) - Grounded in wording; the spec itself is consistent.**
> Spec P1-AC9 already defines "new" as "genuine, open, not marked `notified`", so "new" and "pending" are the same thing there. T17's test text "no new items" reads like "nothing newly discovered", which is a different condition. T17 also lacks a test for the retry itself: a run that discovers nothing new but still has items left un-notified by an earlier failed send.
> **Proposed fix:** in T17, rename that test to "no pending (not yet notified) items gives no email", and add "a previous send failed, nothing newly discovered today, so the pending items are emailed and then marked `notified`" (P1-AC9, P1-AC23).
> **Applied 2026-09-22:** T17 test renamed to "no pending items" and a retry-after-failed-send test added.

6. Medium: “no new items” is ambiguous in T17.
The test says no email when there are no new items, but the design requires retrying previously discovered, unnotified items after a skipped or failed send. The test should distinguish “no pending unnotified items” from “no newly discovered items.”

> **Analysis of item 7 (Claude, 2026-09-22) - Grounded.**
> T12 lists four paths, and its "Jev fails and fallback succeeds" case doesn't say which verdict the fallback returns. `classify` must pass the fallback's verdict through faithfully either way. Where that verdict ends up (storage, report, email) is decided in `state` (T7) and `run` (T17), not in `classify`.
> **Proposed fix:** split that T12 test into two: fallback says genuine (verdict `genuine`, `method="free_fallback"`, degraded failure recorded) and fallback says false positive (verdict `false_positive`, degraded failure still recorded). Add one T17 case: a degraded false positive is stored as `false_positive`, is not reported, and still triggers the failure report.
> **Applied 2026-09-22:** T12 now lists five paths (fallback genuine / fallback false positive split); T17 gained the degraded-false-positive case.

7. Medium: T12’s test matrix omits fallback false-positive behavior.
It lists fallback success generally, but fallback success can produce either genuine or false_positive. Both outcomes affect storage, reporting, and notification and should have explicit tests.

> **Analysis of item 8 (Claude, 2026-09-22) - Grounded.**
> T16's done-when (`tasks.md:480`) points at a check that only exists in T17, so T16 cannot honestly be marked done when it is committed. That breaks the skill's rule that every task is verified by its own gate.
> **Proposed fix:** give T16 its own test: a unit test in `tests/test_report.py` runs `update_readme` on a copy of the real `README.md` and asserts both markers appear exactly once and content outside them is untouched. T16's `Tests` changes from `none` to `unit` and its gate to `quick`, which also removes one validator warning.
> **Applied 2026-09-22:** T16 now has its own unit test on a copy of the real `README.md`; `Tests: unit`, `Gate: quick`.

8. Low: T16’s validation is deferred oddly.
T16 says its real-file integration check happens in T17, but T16 itself is marked complete before T17 runs. Either move that check to T17 explicitly or add a small test at T16.

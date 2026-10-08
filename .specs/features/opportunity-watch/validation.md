# Opportunity Watch Validation

**Verdict**: PASS ✅ (iteration 2; the fixes were test-only, production code unchanged)

**Date**: 2026-10-08
**Spec**: `.specs/features/opportunity-watch/spec.md`
**Diff range**: `f95e0d4..b4aa2b5` (commits `3b0dd45`..`b4aa2b5`) plus the uncommitted iteration-2 changes to three test files
**Verifier**: independent sub-agent (author ≠ verifier)

The code meets the spec on every path I traced. Iteration 1 returned FAIL because 3 non-equivalent mutants survived and P3-AC1 had no test evidence. Iteration 2 confirms the three test-only fixes. All 21 non-equivalent mutants are now killed.

## Iteration 2 (fix iteration 1 of 3)

- **Changes checked**: `tests/test_run.py` (P3-AC1 log line, `:223-226`), `tests/test_validate.py` (new 0.5 boundary test, `:94-98`), `tests/test_notify.py` (new empty-maintainer warning test, `:137-141`). `git diff -- src config .github` is empty, so no production code changed.
- **Gate**: ruff check passes; ruff format passes (16 files); pytest has 88 passed, 0 failed, 0 skipped (86 + 2 new tests).
- **Sensor**: the full set was re-run in fresh copies (`scratchpad/verifier/<mutant>_it2/`). M06, M13 and M21 are now killed. The other 18 non-equivalent mutants are still killed, and the equivalent M10 still survives as expected.
- **Citations**: test line numbers in this report were renumbered to the current files, because the new tests shifted later lines.

**Live e2e pending.** T19 (the dispatched `workflow_dispatch` run) has not run yet. It is blocked on the user creating the Gmail account and the five secrets. ACs that only a live run can prove are marked "deferred to T19". They are not counted as failed.

---

## Task Completion

| Task | Status | Notes |
| --- | --- | --- |
| T1–T18 | ✅ Done | All "Done when" boxes ticked in `tasks.md`; code and tests present in the diff |
| T19 | ⏳ Pending | Manual e2e; blocked on the user's Gmail account, App Password and secrets |

---

## Gate Check

- **Gate command**: `uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
- **Result (iteration 2)**: ruff check: all checks passed. ruff format: 16 files already formatted. pytest: **88 passed, 0 failed, 0 skipped** (0.49s). Iteration 1: 86 passed.
- **Test count before feature**: 0 (new repository)
- **Test count after feature**: 88
- **Delta**: +88
- **Skipped tests**: none
- **Failures**: none

---

## Spec-Anchored Acceptance Criteria

### P1

| AC | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| P1-AC1 | Cron `0 11 * * *` and `workflow_dispatch`; every configured query runs | `.github/workflows/opportunity-watch.yml:6-7` (static). `tests/test_run.py:176` - `"summary: queries_run=2 ..." in text`; `tests/test_run.py:293` - `[m["to"] for m in world.sent] == [RECIPIENTS, MAINTAINERS]` (Q2 failure proves Q2 also ran) | ✅ PASS (code); cron firing deferred to T19 |
| P1-AC2 | title, URL, source site extracted | `tests/test_search.py:23` - `[(r.title, r.url, r.body, r.source_site, r.query) ...] == [("Edital 12/2026", "https://unila.edu.br/e/12", "PSS", "unila.edu.br", q)]` | ✅ PASS |
| P1-AC3 | Missing title or URL dropped, rest kept | `tests/test_search.py:38` - `[r.title for r in results] == ["Kept"]` | ✅ PASS |
| P1-AC4 | New ids classified; stored ids never re-classified | `tests/test_state.py:101` - `store.diff_new(["g","new","fp"]) == ["new"]`; `tests/test_run.py:200` - `world.jev_urls == []` | ✅ PASS |
| P1-AC5 | False positive excluded from report and email, stored as `false_positive` | `tests/test_state.py:110-111` - `verdict == "false_positive"`, `open_ids(result) == ["g"]`; `tests/test_run.py:253-255` - `verdict == "false_positive"`, `url(1) not in world.readme()`, `emails_to(RECIPIENTS) == []` | ✅ PASS |
| P1-AC6 | Jev failure retries with free-tier only (`openrouter/free`) | `tests/test_validate.py:133` - `call["json"]["model"] == "openrouter/free"`; `tests/test_validate.py:118-121` - HTTP error, timeout, malformed JSON, missing answer each raise `JevCallError` | ✅ PASS |
| P1-AC7 | Both fail: excluded from report and email, logged, not stored | `tests/test_run.py:264-268` - `stored(1).id not in world.seen()`, `url(1) not in world.readme()`, `"type: validation (excluded)" in alert["body"]`, `"excluded=1" in ...out`; retry next run `tests/test_run.py:273` - `verdict == "genuine"` | ✅ PASS |
| P1-AC8 | id = SHA-256 of normalized URL | `tests/test_state.py:59` - `opportunity_id("https://UNILA.edu.br/editais/42/") == sha256(b"https://unila.edu.br/editais/42").hexdigest()`; `tests/test_state.py:42` equivalents share an id | ✅ PASS |
| P1-AC9 | New = genuine, open, not notified | `tests/test_state.py:165` - `[c.id for c in store.pending_notification()] == ["new"]` (excludes fp, stale, notified) | ✅ PASS |
| P1-AC10 | Exactly one email listing only new items; all recipients in Bcc (envelope), To = sender | `tests/test_notify.py:65-69` - `To == SENDER`, `mail["to"] == RECIPIENTS`, no address in headers; `tests/test_notify.py:93` - `body.count("https://") == 2`; `tests/test_run.py:170-172` - one mail, `to == RECIPIENTS` | ✅ PASS |
| P1-AC11 | No new items: no email | `tests/test_run.py:199` - `world.sent == []`; `tests/test_notify.py:101-102` | ✅ PASS |
| P1-AC12 | README section rewritten every run with the full open set | `tests/test_run.py:164` - `url(1) in world.readme() and url(2) in ...`; `tests/test_report.py:51` - exact file text; `tests/test_report.py:45` - empty line text | ✅ PASS |
| P1-AC13 | Removed after 3 consecutive counted misses | `tests/test_state.py:118-120` - open `["a"]` for runs 1-2, `[]` at run 3, `miss_count == 3`; `tests/test_run.py:232-233` | ✅ PASS |
| P1-AC14 | id kept 30 days after `last_seen`, then purged | `tests/test_state.py:136-137` - `result.purged == ["day31"]`, `set(store.opportunities) == {"day30"}` | ✅ PASS |
| P1-AC15 | Commit `seen.json` and README when either changed | `.github/workflows/opportunity-watch.yml:42-48` (static: `git add`, `git diff --cached --quiet` guard, commit, push); `tests/test_report.py:59-60` - unchanged input returns `False`, bytes equal; `src/opportunity_watch/state.py:80` sorted save | ⏳ Deferred to T19 (real commit/push); static path correct |
| P1-AC16 | Email failure logged; report still published (exit 0) | `tests/test_run.py:280-282` - `run.main() == 0`, `notified is False`, `url(1) in world.readme()` | ✅ PASS |
| P1-AC17 | Concurrency group | `.github/workflows/opportunity-watch.yml:9-11` - `group: opportunity-watch`, `cancel-in-progress: false` (static; no test) | ⏳ Deferred to T19; static evidence only |
| P1-AC18 | Summary: queries, candidates, validated, new, errors | `tests/test_run.py:175-176` - `"summary: queries_run=2 candidates_found=2 validated=2 new=2 excluded=0 failures=0" in text` | ✅ PASS |
| P1-AC19 | Jev fails, fallback succeeds: candidate kept, failure recorded, maintainer email fires | `tests/test_validate.py:192-196` - `(verdict, method) == (verdict, "free_fallback")`, `[(type,target,excluded)] == [("validation", url, False)]`; `tests/test_run.py:242-245` - in README, in recipient email, one alert with `target: {url(1)}` | ✅ PASS |
| P1-AC20 | Exact question text; affirmative = genuine (design: below 0.5 is a false positive, so 0.5 is genuine) | `tests/test_validate.py:81` - `question["instructions"] == P1_AC20_QUESTION`; `tests/test_validate.py:94-98` - `_call_jev(...) == JevAnswer(genuine=True, probability=0.5)`; `tests/test_validate.py:89-91`, `:103-105` - 0.51 genuine, 0.49 false positive | ✅ PASS (iteration 2; the spec's "affirmative" is made precise by the design threshold) |
| P1-AC21 | Run with a failed query does not count a miss | `tests/test_state.py:126` - `miss_count == 2`; `tests/test_run.py:218-219` - `miss_count == 2`, still in README | ✅ PASS |
| P1-AC22 | Reappearing retained id restored, not re-classified, not re-notified | `tests/test_state.py:144-145` - `(miss_count, last_seen, notified) == (0, "2026-10-07", True)`, open; `tests/test_run.py:199-200` - no email, `jev_urls == []` | ✅ PASS |
| P1-AC23 | `notified` set only after a successful send; failed or skipped stays pending | `tests/test_run.py:166-169` - both `("genuine", True)`; `tests/test_run.py:281` - `notified is False` after send failure; `tests/test_run.py:336` - `notified is False` with empty list | ✅ PASS |

### P2a

| AC | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| P2a-AC1 | Queries read from version-controlled config | `tests/test_config.py:41` - `load_queries(...) == ['site:a.br "x"', "site:b.br y"]`; `tests/test_config.py:64-65` - shipped file has 8 `site:` queries | ✅ PASS |
| P2a-AC2 | Recipient list from a secret, not a file | `tests/test_config.py:30` - `load_address_list("OPPORTUNITY_RECIPIENTS") == ["a@example.com", "b@example.com"]`; workflow `:33` maps the secret | ✅ PASS |
| P2a-AC3 | New query picked up with no code change | `tests/test_run.py:54` writes the queries file, `:176` - `queries_run=2` comes from the file | ✅ PASS (live check deferred to T19) |

### P2b

| AC | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| P2b-AC1 | One failure report per run with any failure (search, degraded, excluded, email) | `tests/test_run.py:220` (search), `:244` (degraded), `:266` (excluded), `:283-285` (email) - each `(alert,) = world.emails_to(MAINTAINERS)` plus the type in the body | ✅ PASS |
| P2b-AC2 | Zero failures: no report | `tests/test_run.py:173` - `world.emails_to(MAINTAINERS) == []`; `tests/test_notify.py:133-134` | ✅ PASS |
| P2b-AC3 | Lists type, target, error per failure | `tests/test_notify.py:119-122` - `type:`, `target:`, `error:` lines for each failure | ✅ PASS |
| P2b-AC4 | Maintainer list from its own newline-separated secret | `tests/test_config.py:35`; `tests/test_run.py:64` (`MAINTAINER_ALERTS` separate from recipients), `:293` distinct envelopes | ✅ PASS |
| P2b-AC5 | Both due: two separate emails | `tests/test_run.py:293` - `[m["to"] for m in world.sent] == [RECIPIENTS, MAINTAINERS]` | ✅ PASS |
| P2b-AC6 | Crash after secrets: one best-effort report, then non-zero exit | `tests/test_run.py:299-304` - `pytest.raises(ReportError)`, one alert with `"type: unexpected"` and `"ReportError"`, `"partial summary: ..."` | ✅ PASS |
| P2b-AC7 | Crash before secrets: no report attempt | `tests/test_run.py:310-313` - `ConfigError` raised, `world.sent == []`; `tests/test_run.py:327-328` - subprocess `returncode == 1` | ✅ PASS |
| P2b-AC8 | Failure report in Bcc, To = sender | `tests/test_notify.py:123` - `To == SENDER`; `tests/test_run.py:220` - envelope `== MAINTAINERS`; shared `_send` path covered by `tests/test_notify.py:65-69` | ✅ PASS |

### P3

| AC | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| P3-AC1 | Log the failing step, target and error to the run log; email target is a count | `tests/test_run.py:223-226` - `f"failure: type=search excluded=False target={Q1} error=RatelimitException: 202 Ratelimit" in out`; email target as a count: `tests/test_notify.py:149` - `target == "new-opportunity email to 2 recipient(s)"` | ✅ PASS (iteration 2) |
| P3-AC2 | Summary printed even when steps failed | `tests/test_run.py:304` - `"partial summary: queries_run=2 candidates_found=1" in text`; `tests/test_run.py:268` - `"excluded=1"` on a failed-candidate run | ✅ PASS |

### AD-001 (no raw address in logs)

| Check | `file:line` + assertion | Result |
| --- | --- | --- |
| No address in SMTP error text | `tests/test_notify.py:77` - `str(exc.value) == "SMTPRecipientsRefused"`, `:78` `__cause__ is None`, `:80` no address in output | ✅ PASS |
| No address in returned failure or output | `tests/test_notify.py:155` | ✅ PASS |
| No address in run stdout/stderr (clean, email-failure, crash runs) | `tests/test_run.py:174`, `:286`, `:303` - `assert_no_address(capsys)` | ✅ PASS |
| Public Actions log | Workflow never echoes secrets (`.github/workflows/opportunity-watch.yml:29-36`) | ⏳ Deferred to T19 (live log) |

**Status**: 34 of 36 ACs covered with a matching asserted value. 0 gaps. 0 open spec-precision gaps. P1-AC15 and P1-AC17 have static evidence only and are deferred to T19.

---

## Edge Cases

- [x] Zero results is not an error: `tests/test_search.py:54` - `run_searches([q]) == ([], [])`
- [x] Same URL from two queries deduped before validation: `tests/test_run.py:192` - `seen_snippets == ["snippet 1"]` (classified once)
- [x] First-ever run, no `seen.json`: `tests/test_state.py:67-68`
- [x] Backend error for one query: logged, skipped, others continue: `tests/test_search.py:46-48`
- [x] Empty recipient secret: README updated, no email, warning, items stay pending: `tests/test_run.py:335-338`
- [x] Empty maintainer secret: skip asserted (`tests/test_notify.py:133-134`); warning asserted at `tests/test_notify.py:140` - `"warning: maintainer list is empty; failure report with 1 items skipped" in out`, plus `assert_no_address(out)` (iteration 2)
- [x] Git push fails after emails sent: accepted duplicate; follows from `seen.json` only being persisted by the commit step (design, deferred to T19)
- [x] Crash before secrets: `tests/test_run.py:310-313`, `:327`
- [x] Crash after secrets: `tests/test_run.py:299-304`

---

## Discrimination Sensor

Run in isolated copies under the session scratchpad (`.../scratchpad/verifier/<mutant>/`, copying `src tests config pyproject.toml uv.lock README.md`). Each copy ran `uv run pytest -q -x`. The baseline copy passed 86/86.

| # | File | Mutation | Result |
| --- | --- | --- | --- |
| M01 | `state.py:58` | `elif count_misses:` → `else:` (ignore P1-AC21 flag) | ✅ Killed |
| M02 | `state.py:39` | `miss_count < 3` → `<= 3` (stale off-by-one) | ✅ Killed |
| M03 | `state.py:63` | purge `> 30` → `>= 30` | ✅ Killed |
| M04 | `state.py:54` | `setdefault` → overwrite stored verdict/notified | ✅ Killed |
| M05 | `validate.py:123` | degraded fallback returns no `FailureRecord` (P1-AC19) | ✅ Killed |
| M06 | `validate.py:83` | `probability >= 0.5` → `> 0.5` | ✅ Killed in iteration 2 (iteration 1: survived) |
| M07 | `notify.py:22` | add a `Bcc:` header with all recipients (AD-001 / P1-AC10) | ✅ Killed |
| M08 | `notify.py:31` | `SendError` carries `str(e)` (address leak) | ✅ Killed |
| M09 | `run.py:72` | mark notified even when the send was skipped | ✅ Killed |
| M10 | `run.py:69` | extra `save` before the send (original post-send save kept) | ⚪ Equivalent (final file identical) |
| M10b | `run.py:69-75` | `save` only before the send (true reorder) | ✅ Killed |
| M11 | `run.py:102` | no failure report on unexpected exception | ✅ Killed |
| M12 | `run.py:104` | swallow the exception and return 0 | ✅ Killed |
| M13 | `run.py:17-18` | drop the per-failure log lines (P3-AC1) | ✅ Killed in iteration 2 (iteration 1: survived) |
| M14 | `report.py:36` | drop the text after the END marker | ✅ Killed |
| M15 | `search.py:37` | `continue` → `break` after a failed query | ✅ Killed |
| M16 | `run.py:64` | always count misses (P1-AC21) | ✅ Killed |
| M17 | `run.py:69` | email the whole open set instead of pending | ✅ Killed |
| M18 | `run.py:77` | failure report only when something was excluded | ✅ Killed |
| M19 | `validate.py:13` | fallback model `openrouter/auto` (paid risk) | ✅ Killed |
| M20 | `run.py:58` | store a candidate whose validation failed | ✅ Killed |
| M21 | `notify.py:67` | drop the empty-maintainer-list warning | ✅ Killed in iteration 2 (iteration 1: survived) |

**Sensor depth**: expanded (22 mutants; data-integrity and AD-001 paths).
**Result**: iteration 2: 21 killed, 0 survived, 1 equivalent (M10) → PASS ✅. Iteration 1 was 18 killed, 3 survived.

**Real-tree isolation (iteration 2)**: before the sensor, `git status --porcelain` showed `M` on the three fixed test files and `??` on `validation.md` and `latest_session.md`. Afterwards it showed the same entries plus ` M CLAUDE.md`. That `CLAUDE.md` edit was made outside the sensor while it was running. It updates the "Status" and "Spec tooling" docs and applies the iteration-1 finding that `validate_state.py` must run from the repo root. The sensor only writes under the scratchpad. `git status -- src tests config .github README.md pyproject.toml uv.lock` showed only the three fixed test files, so the code under test was unchanged.

**Real-tree isolation (iteration 1)**: `git status --porcelain` before the sensor: `?? latest_session.md`. After: `?? latest_session.md` (identical; `diff` returned no output). No `git stash` was used.

---

## Correctness Review (beyond the tests)

No production bug found. Paths checked:

- Ordering: `mark_notified` runs only after a successful send, then `save` (`run.py:69-75`). Correct for P1-AC23.
- Failure boundary: secrets load outside the `try` (`run.py:85-86`); everything else is inside it; the exception is re-raised for a non-zero exit (`run.py:104`).
- Stale and purge: misses count only on clean runs; purge after more than 30 days since `last_seen`; false positives keep a refreshed `last_seen` while they still appear, so they are not re-classified.
- Workflow: commit only if `git diff --cached --quiet` reports changes. The commit step is skipped when the script exits non-zero, which is correct. Action tags `actions/checkout@v7` and `astral-sh/setup-uv@v10.2.0` exist (checked with `gh api`).

Low-risk notes (no fix required for v1):

1. AD-001 residual: an unexpected exception's text is printed and emailed as is (`run.py:97`), and Python prints the traceback. Today nothing on that path puts an address in an exception message (SMTP errors are reduced to the type name). A future change that does would leak it.
2. `report._escape` escapes only `[` and `]`. A URL containing `)` or a space would break that Markdown link in the README. This is cosmetic.
3. The `~typesafe/jev-latest` alias may be rejected by the Decisions API (design Risks). T19 will show this; the fix is the `JEV_MODEL` variable.

---

## Code Quality

| Principle | Status |
| --- | --- |
| Minimum code | ✅ |
| Surgical changes | ✅ |
| No scope creep | ✅ |
| Matches patterns | ✅ |
| Spec-anchored outcome check | ✅ |
| Per-layer coverage (domain 1:1 ACs; orchestrator happy + edge + error) | ✅ |
| Every test maps to an AC, edge case or Done-when | ✅ |
| Documented guidelines followed: `CLAUDE.md`, `.specs/STATE.md` (AD-001) | ✅ |

---

## Fix Plans

All three fixes were applied in iteration 2 and verified (their mutants are now killed).

### Fix 1: Assert the per-failure log line (P3-AC1) - Major - ✅ Done (iteration 2)

- **Root cause**: no test reads the `failure: type=... target=... error=...` line from `run._print_summary`.
- **Fix task**: in `tests/test_run.py::test_query_failure_sends_report_and_counts_no_miss` (or a new test), capture stdout and assert `f"failure: type=search excluded=False target={Q1} error=RatelimitException: 202 Ratelimit"` is in it.
- **Done when**: mutant M13 is killed.

### Fix 2: Pin the Jev threshold boundary (P1-AC20 / design threshold) - Minor - ✅ Done (iteration 2)

- **Fix task**: add `jev_reply(0.5)` → `JevAnswer(genuine=True, probability=0.5)` to `tests/test_validate.py`.
- **Done when**: mutant M06 is killed.

### Fix 3: Assert the empty-maintainer warning (edge case) - Minor - ✅ Done (iteration 2)

- **Fix task**: in `tests/test_notify.py::test_failure_report_skips_without_failures_or_maintainers` (empty-list case) or a run-level test with `MAINTAINER_ALERTS=""`, assert `"warning: maintainer list is empty"` is in stdout.
- **Done when**: mutant M21 is killed.

---

## Requirement Traceability Update

| Requirement | New status |
| --- | --- |
| OPW-01, 02, 03, 04, 05, 08, 09, 10 | Verified (unit and integration); live check pending T19 |
| OPW-06 (P1-AC14, AC15) | AC14 verified; AC15 deferred to T19 |
| OPW-07 (P1-AC17, AC18) | AC18 verified; AC17 deferred to T19 |
| OPW-11 (P3) | Verified (iteration 2) |

---

## Summary

**Overall**: ✅ Ready for T19. All code-level checks pass. Live e2e is still pending.

**Spec-anchored check**: 34/36 ACs matched spec outcome. 0 gaps. 2 deferred to T19 (P1-AC15, P1-AC17).
**Sensor**: 21/21 non-equivalent mutants killed (1 equivalent).
**Gate**: 88 passed, 0 failed.

**Next steps**: the user commits the three test changes, then runs T19.

from datetime import datetime
from zoneinfo import ZoneInfo

from opportunity_watch import config, notify, report, search, state, validate
from opportunity_watch.models import Candidate, FailureRecord, RunSummary, utc_timestamp

QUERIES_PATH = "config/queries.yaml"
SEEN_PATH = "data/seen.json"
README_PATH = "README.md"
REQUIRED_SECRETS = ("OPENROUTER_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD")
# why: dates in seen.json and the README follow the 08:00 Brasília schedule, not the runner clock.
TIMEZONE = ZoneInfo("America/Sao_Paulo")


def _print_summary(summary: RunSummary, partial: bool = False) -> None:
    # invariant: counts, queries and candidate URLs only, never an address (AD-001).
    for f in summary.failures:
        print(f"failure: type={f.type} excluded={f.excluded} target={f.target} error={f.message}")
    print(
        f"{'partial ' if partial else ''}summary: queries_run={summary.queries_run} "
        f"candidates_found={summary.candidates_found} validated={summary.validated_count} "
        f"new={summary.new_count} excluded={summary.excluded_count} "
        f"failures={len(summary.failures)}"
    )


def _run(summary: RunSummary, recipients: list[str], maintainers: list[str]) -> None:
    queries = config.load_queries(QUERIES_PATH)
    summary.queries_run = len(queries)
    raw_results, search_failures = search.run_searches(queries)
    summary.failures.extend(search_failures)

    first_result = {}
    for raw in raw_results:
        first_result.setdefault(state.opportunity_id(raw.url), raw)
    summary.candidates_found = len(first_result)

    store = state.load_seen(SEEN_PATH)
    today = datetime.now(TIMEZONE).date()
    new_candidates = []
    for id_ in store.diff_new(list(first_result)):
        raw = first_result[id_]
        candidate = Candidate(
            id=id_,
            title=raw.title,
            url=raw.url,
            source_site=raw.source_site,
            first_seen=today.isoformat(),
            last_seen=today.isoformat(),
            miss_count=0,
            verdict="genuine",
            notified=False,
        )
        result, failures = validate.classify(candidate, raw.body)
        summary.failures.extend(failures)
        if result.verdict == "failed":
            summary.excluded_count += 1
            continue
        summary.validated_count += 1
        candidate.verdict = result.verdict
        new_candidates.append(candidate)

    # why: a run with a failed query must not count toward the 3-miss rule (P1-AC21).
    run_state = store.apply_run(set(first_result), new_candidates, today, not search_failures)
    report.update_readme(README_PATH, report.render_section(run_state.open))

    pending = store.pending_notification()
    summary.new_count = len(pending)
    sent = notify.send_new_opportunities(pending, recipients)
    if sent.failure:
        summary.failures.append(sent.failure)
    elif not sent.skipped:
        store.mark_notified([c.id for c in pending])
    # why: saved after the send, so `notified` reflects what was actually emailed (P1-AC23).
    store.save(SEEN_PATH)

    if summary.failures:
        alert = notify.send_failure_report(list(summary.failures), maintainers)
        if alert.failure:
            summary.failures.append(alert.failure)


def main() -> int:
    # why: outside the try - without credentials no failure email is possible (P2b-AC7).
    for name in REQUIRED_SECRETS:
        config.require_env(name)
    recipients = config.load_address_list("OPPORTUNITY_RECIPIENTS")
    maintainers = config.load_address_list("MAINTAINER_ALERTS")
    summary = RunSummary(0, 0, 0, 0, 0, [])
    try:
        _run(summary, recipients, maintainers)
    except Exception as e:
        summary.failures.append(
            FailureRecord(
                type="unexpected",
                target="run.main",
                message=f"{type(e).__name__}: {e}",
                timestamp=utc_timestamp(),
            )
        )
        # why: best effort only (P2b-AC6); notify returns send errors instead of raising.
        notify.send_failure_report(summary.failures, maintainers)
        _print_summary(summary, partial=True)
        raise
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

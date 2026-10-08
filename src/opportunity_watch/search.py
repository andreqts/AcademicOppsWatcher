import re

from ddgs import DDGS
from ddgs.exceptions import DDGSException

from opportunity_watch.models import FailureRecord, RawResult, utc_timestamp

MAX_RESULTS = 20
# hazard: ddgs raises this instead of returning [] when a query has no hits.
NO_RESULTS_MESSAGE = "No results found."


def _site(query: str) -> str:
    match = re.search(r"site:(\S+)", query)
    return match.group(1) if match else ""


def run_searches(queries: list[str]) -> tuple[list[RawResult], list[FailureRecord]]:
    results: list[RawResult] = []
    failures: list[FailureRecord] = []
    client = DDGS()
    for query in queries:
        try:
            hits = client.text(query, max_results=MAX_RESULTS)
        # why: any error from one query must not abort the others (spec edge case).
        except Exception as e:  # noqa: BLE001
            if isinstance(e, DDGSException) and str(e) == NO_RESULTS_MESSAGE:
                continue
            failures.append(
                FailureRecord(
                    type="search",
                    target=query,
                    message=f"{type(e).__name__}: {e}",
                    timestamp=utc_timestamp(),
                )
            )
            continue
        for hit in hits:
            if hit.get("title") and hit.get("href"):
                results.append(
                    RawResult(
                        title=hit["title"],
                        url=hit["href"],
                        body=hit.get("body", ""),
                        source_site=_site(query),
                        query=query,
                    )
                )
    return results, failures

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from opportunity_watch.models import Candidate

STALE_AFTER_MISSES = 3
PURGE_AFTER_DAYS = 30


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not k.startswith("utm_")
        ]
    )
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, "")
    )


def opportunity_id(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()


@dataclass
class RunStateResult:
    open: list[Candidate]
    purged: list[str]


def _is_open(c: Candidate) -> bool:
    return c.verdict == "genuine" and c.miss_count < STALE_AFTER_MISSES


class SeenStore:
    def __init__(self, opportunities: dict[str, Candidate]):
        self.opportunities = opportunities

    def diff_new(self, candidate_ids: list[str]) -> list[str]:
        return [i for i in candidate_ids if i not in self.opportunities]

    def apply_run(
        self, found_ids: set[str], new_candidates: list[Candidate], today: date, count_misses: bool
    ) -> RunStateResult:
        for c in new_candidates:
            # invariant: a stored verdict or notified flag is never overwritten.
            self.opportunities.setdefault(c.id, c)
        for id_, c in self.opportunities.items():
            if id_ in found_ids:
                c.last_seen, c.miss_count = today.isoformat(), 0
            elif count_misses:
                c.miss_count += 1
        purged = [
            id_
            for id_, c in self.opportunities.items()
            if (today - date.fromisoformat(c.last_seen)).days > PURGE_AFTER_DAYS
        ]
        for id_ in purged:
            del self.opportunities[id_]
        return RunStateResult([c for c in self.opportunities.values() if _is_open(c)], purged)

    def pending_notification(self) -> list[Candidate]:
        return [c for c in self.opportunities.values() if _is_open(c) and not c.notified]

    def mark_notified(self, ids: list[str]) -> None:
        for id_ in ids:
            self.opportunities[id_].notified = True

    def save(self, path: str) -> None:
        data = {
            "opportunities": {
                id_: {k: v for k, v in asdict(c).items() if k != "id"}
                for id_, c in sorted(self.opportunities.items())
            }
        }
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")


def load_seen(path: str) -> SeenStore:
    if not os.path.exists(path):
        return SeenStore({})
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)["opportunities"]
    return SeenStore({id_: Candidate(id=id_, **fields) for id_, fields in raw.items()})

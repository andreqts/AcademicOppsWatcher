from datetime import date, timedelta

from opportunity_watch.models import Candidate
from opportunity_watch.state import SeenStore, load_seen, normalize_url, opportunity_id

TODAY = date(2026, 10, 7)


def make(id_, verdict="genuine", last_seen=TODAY, miss_count=0, notified=False):
    return Candidate(
        id=id_,
        title=f"Edital {id_}",
        url=f"https://unila.edu.br/{id_}",
        source_site="unila.edu.br",
        first_seen=last_seen.isoformat(),
        last_seen=last_seen.isoformat(),
        miss_count=miss_count,
        verdict=verdict,
        notified=notified,
    )


def store_with(*candidates):
    return SeenStore({c.id: c for c in candidates})


def open_ids(result):
    return [c.id for c in result.open]


# T5: normalization and id (P1-AC8)


def test_equivalent_urls_share_an_id():
    base = opportunity_id("https://unila.edu.br/editais/42")
    variants = [
        "HTTPS://UNILA.EDU.BR/editais/42",
        "https://unila.edu.br/editais/42#anexo",
        "https://unila.edu.br/editais/42?utm_source=x&utm_medium=y",
        "https://unila.edu.br/editais/42/",
    ]
    assert [opportunity_id(v) for v in variants] == [base] * 4


def test_non_tracking_query_params_are_kept():
    assert normalize_url("https://a.br/p?id=7&utm_campaign=z") == "https://a.br/p?id=7"


def test_different_paths_give_different_ids():
    assert opportunity_id("https://unila.edu.br/editais/42") != opportunity_id(
        "https://unila.edu.br/editais/43"
    )


def test_id_is_sha256_hex_of_normalized_url():
    import hashlib

    expected = hashlib.sha256(b"https://unila.edu.br/editais/42").hexdigest()
    assert opportunity_id("https://UNILA.edu.br/editais/42/") == expected


# T6: load, save, diff_new (P1-AC4)


def test_first_run_missing_file_is_empty_and_everything_is_new(tmp_path):
    store = load_seen(str(tmp_path / "seen.json"))
    assert store.opportunities == {}
    assert store.diff_new(["a", "b"]) == ["a", "b"]


def test_save_load_round_trip_preserves_every_field(tmp_path):
    path = tmp_path / "data" / "seen.json"
    original = store_with(make("a", notified=True, miss_count=2), make("b", "false_positive"))
    original.save(str(path))
    assert load_seen(str(path)).opportunities == original.opportunities


def test_save_writes_the_design_json_shape(tmp_path):
    import json

    path = tmp_path / "seen.json"
    store_with(make("a")).save(str(path))
    assert json.loads(path.read_text()) == {
        "opportunities": {
            "a": {
                "url": "https://unila.edu.br/a",
                "title": "Edital a",
                "source_site": "unila.edu.br",
                "first_seen": "2026-10-07",
                "last_seen": "2026-10-07",
                "miss_count": 0,
                "verdict": "genuine",
                "notified": False,
            }
        }
    }


def test_diff_new_excludes_genuine_and_false_positive_entries():
    store = store_with(make("g"), make("fp", "false_positive"))
    assert store.diff_new(["g", "new", "fp"]) == ["new"]


# T7: apply_run


def test_false_positive_is_stored_but_never_open():
    store = SeenStore({})
    result = store.apply_run({"fp", "g"}, [make("fp", "false_positive"), make("g")], TODAY, True)
    assert store.opportunities["fp"].verdict == "false_positive"
    assert open_ids(result) == ["g"]


def test_absent_three_counted_runs_leaves_open_set():
    store = store_with(make("a"))
    for run in range(1, 4):
        result = store.apply_run(set(), [], TODAY + timedelta(days=run), True)
        expected = ["a"] if run < 3 else []
        assert open_ids(result) == expected
    assert store.opportunities["a"].miss_count == 3


def test_uncounted_runs_never_increment_miss_count():
    store = store_with(make("a", miss_count=2))
    result = store.apply_run(set(), [], TODAY, False)
    assert store.opportunities["a"].miss_count == 2
    assert open_ids(result) == ["a"]


def test_purge_only_after_30_days_since_last_seen():
    store = store_with(
        make("day30", last_seen=TODAY - timedelta(days=30), miss_count=5),
        make("day31", last_seen=TODAY - timedelta(days=31), miss_count=5),
    )
    result = store.apply_run(set(), [], TODAY, True)
    assert result.purged == ["day31"]
    assert set(store.opportunities) == {"day30"}


def test_reappearing_id_returns_open_with_reset_misses_and_notified_kept():
    store = store_with(make("a", last_seen=TODAY - timedelta(days=5), miss_count=4, notified=True))
    result = store.apply_run({"a"}, [], TODAY, True)
    entry = store.opportunities["a"]
    assert (entry.miss_count, entry.last_seen, entry.notified) == (0, "2026-10-07", True)
    assert open_ids(result) == ["a"]


def test_already_seen_id_keeps_stored_verdict_and_notified():
    store = store_with(make("fp", "false_positive"), make("g", notified=True))
    store.apply_run({"fp", "g"}, [make("fp"), make("g")], TODAY, True)
    assert store.opportunities["fp"].verdict == "false_positive"
    assert store.opportunities["g"].notified is True


# T8: pending_notification and mark_notified (P1-AC9, P1-AC23)


def test_pending_excludes_false_positive_stale_and_notified():
    store = store_with(
        make("new"),
        make("fp", "false_positive"),
        make("stale", miss_count=3),
        make("done", notified=True),
    )
    assert [c.id for c in store.pending_notification()] == ["new"]


def test_marked_ids_are_no_longer_pending():
    store = store_with(make("a"), make("b"))
    store.mark_notified(["a"])
    assert [c.id for c in store.pending_notification()] == ["b"]


def test_unmarked_ids_stay_pending_after_reload(tmp_path):
    path = str(tmp_path / "seen.json")
    store_with(make("a"), make("b")).save(path)
    assert [c.id for c in load_seen(path).pending_notification()] == ["a", "b"]

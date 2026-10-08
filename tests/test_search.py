from ddgs.exceptions import DDGSException, RatelimitException

from opportunity_watch import search


def fake_ddgs(monkeypatch, responses):
    class FakeDDGS:
        def text(self, query, max_results):
            outcome = responses[query]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(search, "DDGS", FakeDDGS)


def test_fields_are_extracted(monkeypatch):
    q = 'site:unila.edu.br "professor substituto"'
    hit = {"title": "Edital 12/2026", "href": "https://unila.edu.br/e/12", "body": "PSS"}
    fake_ddgs(monkeypatch, {q: [hit]})
    results, failures = search.run_searches([q])
    assert failures == []
    assert [(r.title, r.url, r.body, r.source_site, r.query) for r in results] == [
        ("Edital 12/2026", "https://unila.edu.br/e/12", "PSS", "unila.edu.br", q)
    ]


def test_result_missing_title_or_url_is_dropped(monkeypatch):
    q = "site:ifpr.edu.br x"
    hits = [
        {"title": "", "href": "https://ifpr.edu.br/a", "body": ""},
        {"title": "B", "href": "", "body": ""},
        {"title": "C", "body": ""},
        {"title": "Kept", "href": "https://ifpr.edu.br/k", "body": ""},
    ]
    fake_ddgs(monkeypatch, {q: hits})
    results, _ = search.run_searches([q])
    assert [r.title for r in results] == ["Kept"]


def test_failing_query_is_recorded_and_others_still_run(monkeypatch):
    bad, good = "site:a.br x", "site:b.br y"
    hit = {"title": "T", "href": "https://b.br/1", "body": ""}
    fake_ddgs(monkeypatch, {bad: RatelimitException("202 Ratelimit"), good: [hit]})
    results, failures = search.run_searches([bad, good])
    assert [r.url for r in results] == ["https://b.br/1"]
    assert [(f.type, f.target, f.excluded) for f in failures] == [("search", bad, False)]
    assert failures[0].message == "RatelimitException: 202 Ratelimit"


def test_zero_results_is_not_a_failure(monkeypatch):
    q = "site:unioeste.br z"
    fake_ddgs(monkeypatch, {q: DDGSException("No results found.")})
    assert search.run_searches([q]) == ([], [])

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import requests
from ddgs.exceptions import RatelimitException

from opportunity_watch import config, notify, report, run, search, state, validate
from opportunity_watch.models import Candidate

Q1 = 'site:unila.edu.br "professor substituto"'
Q2 = 'site:ifpr.edu.br "processo seletivo simplificado"'
SENDER = "watcher.bot@gmail.com"
RECIPIENTS = ["ana@example.com", "bruno@example.org"]
MAINTAINERS = ["ops@example.net"]
ADDRESSES = [*RECIPIENTS, *MAINTAINERS]
TODAY = datetime.now(run.TIMEZONE).date()


def hit(n, site="unila.edu.br"):
    return {"title": f"Edital {n}", "href": f"https://{site}/editais/{n}", "body": f"snippet {n}"}


def url(n, site="unila.edu.br"):
    return f"https://{site}/editais/{n}"


class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._body


class World:
    def __init__(self, tmp_path, monkeypatch):
        self.root = tmp_path
        self.hits = {Q1: [], Q2: []}
        self.jev = {}
        self.fallback = {}
        self.failing_subjects = []
        self.sent = []
        self.jev_urls = []
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "queries.yaml").write_text(f"queries:\n  - '{Q1}'\n  - '{Q2}'\n")
        (tmp_path / "README.md").write_text(
            f"# Title\n\n{report.START_MARKER}\n{report.EMPTY_LINE}\n{report.END_MARKER}\n"
        )
        monkeypatch.chdir(tmp_path)
        for name, value in {
            "OPENROUTER_API_KEY": "sk-test",
            "GMAIL_ADDRESS": SENDER,
            "GMAIL_APP_PASSWORD": "app-pass",
            "OPPORTUNITY_RECIPIENTS": "\n".join(RECIPIENTS),
            "MAINTAINER_ALERTS": "\n".join(MAINTAINERS),
        }.items():
            monkeypatch.setenv(name, value)
        monkeypatch.delenv("JEV_MODEL", raising=False)
        world = self

        class FakeDDGS:
            def text(self, query, max_results):
                outcome = world.hits[query]
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

        def fake_post(target, json, headers, timeout):
            if target == validate.DECISIONS_URL:
                candidate_url = json["state"]["url"]
                world.jev_urls.append(candidate_url)
                outcome = world.jev.get(candidate_url, 0.9)
                if isinstance(outcome, FakeResponse):
                    return outcome
                return FakeResponse(
                    200, {"answers": {"genuine": {"type": "noul", "noul": outcome}}}
                )
            text = world.fallback[
                next(u for u in world.fallback if u in json["messages"][0]["content"])
            ]
            if isinstance(text, FakeResponse):
                return text
            return FakeResponse(200, {"choices": [{"message": {"content": text}}]})

        class FakeSMTP:
            def __init__(self, host, port, timeout):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def login(self, user, password):
                pass

            def send_message(self, message, from_addr, to_addrs):
                if any(s in message["Subject"] for s in world.failing_subjects):
                    raise notify.smtplib.SMTPServerDisconnected("connection lost")
                world.sent.append(
                    {
                        "subject": message["Subject"],
                        "to": list(to_addrs),
                        "body": message.get_content(),
                    }
                )

        monkeypatch.setattr(search, "DDGS", FakeDDGS)
        monkeypatch.setattr(validate.requests, "post", fake_post)
        monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)

    def seed(self, *candidates):
        state.SeenStore({c.id: c for c in candidates}).save(str(self.root / "data" / "seen.json"))

    def seen(self):
        return json.loads((self.root / "data" / "seen.json").read_text())["opportunities"]

    def readme(self):
        return (self.root / "README.md").read_text()

    def emails_to(self, addresses):
        return [m for m in self.sent if m["to"] == addresses]


def stored(n, verdict="genuine", notified=False, miss_count=0, site="unila.edu.br"):
    return Candidate(
        id=state.opportunity_id(url(n, site)),
        title=f"Edital {n}",
        url=url(n, site),
        source_site=site,
        first_seen=(TODAY - timedelta(days=3)).isoformat(),
        last_seen=(TODAY - timedelta(days=1)).isoformat(),
        miss_count=miss_count,
        verdict=verdict,
        notified=notified,
    )


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


def assert_no_address(capsys):
    out = capsys.readouterr()
    text = out.out + out.err
    assert all(a not in text for a in ADDRESSES)
    return text


def test_clean_run_with_new_items(world, capsys):
    world.hits[Q1] = [hit(1), hit(2)]
    assert run.main() == 0
    assert url(1) in world.readme() and url(2) in world.readme()
    seen = world.seen()
    assert {v["url"]: (v["verdict"], v["notified"]) for v in seen.values()} == {
        url(1): ("genuine", True),
        url(2): ("genuine", True),
    }
    (mail,) = world.sent
    assert mail["to"] == RECIPIENTS
    assert url(1) in mail["body"] and url(2) in mail["body"]
    assert world.emails_to(MAINTAINERS) == []
    text = assert_no_address(capsys)
    assert (
        "summary: queries_run=2 candidates_found=2 validated=2 new=2 excluded=0 failures=0" in text
    )


def test_snippet_of_first_result_reaches_jev(world, monkeypatch):
    world.hits[Q1] = [hit(1)]
    world.hits[Q2] = [{**hit(1), "body": "later duplicate"}]
    seen_snippets = []
    real_classify = validate.classify

    def spy(candidate, snippet):
        seen_snippets.append(snippet)
        return real_classify(candidate, snippet)

    monkeypatch.setattr(validate, "classify", spy)
    run.main()
    assert seen_snippets == ["snippet 1"]


def test_no_pending_items_sends_no_email(world):
    world.seed(stored(1, notified=True))
    world.hits[Q1] = [hit(1)]
    assert run.main() == 0
    assert world.sent == []
    assert world.jev_urls == []
    assert url(1) in world.readme()


def test_retry_after_failed_send_emails_pending_items_and_marks_them(world):
    world.seed(stored(1, notified=False))
    world.hits[Q1] = [hit(1)]
    assert run.main() == 0
    assert world.jev_urls == []
    (mail,) = world.sent
    assert mail["to"] == RECIPIENTS and url(1) in mail["body"]
    assert world.seen()[stored(1).id]["notified"] is True


def test_query_failure_sends_report_and_counts_no_miss(world, capsys):
    world.seed(stored(9, notified=True, miss_count=2))
    world.hits[Q1] = RatelimitException("202 Ratelimit")
    assert run.main() == 0
    assert world.seen()[stored(9).id]["miss_count"] == 2
    assert url(9) in world.readme()
    (alert,) = world.emails_to(MAINTAINERS)
    assert "type: search" in alert["body"] and f"target: {Q1}" in alert["body"]
    out = capsys.readouterr().out
    assert (
        f"failure: type=search excluded=False target={Q1} error=RatelimitException: 202 Ratelimit"
        in out
    )


def test_clean_run_absence_counts_a_miss(world):
    world.seed(stored(9, notified=True, miss_count=2))
    assert run.main() == 0
    assert world.seen()[stored(9).id]["miss_count"] == 3
    assert url(9) not in world.readme()
    assert world.sent == []


def test_jev_degraded_item_is_reported_and_failure_report_sent(world):
    world.hits[Q1] = [hit(1)]
    world.jev[url(1)] = FakeResponse(503)
    world.fallback[url(1)] = "sim"
    assert run.main() == 0
    assert url(1) in world.readme()
    assert url(1) in world.emails_to(RECIPIENTS)[0]["body"]
    (alert,) = world.emails_to(MAINTAINERS)
    assert "type: validation\n" in alert["body"] and f"target: {url(1)}" in alert["body"]


def test_degraded_false_positive_is_stored_not_reported_and_alerts(world):
    world.hits[Q1] = [hit(1)]
    world.jev[url(1)] = FakeResponse(503)
    world.fallback[url(1)] = "não"
    assert run.main() == 0
    assert world.seen()[stored(1).id]["verdict"] == "false_positive"
    assert url(1) not in world.readme()
    assert world.emails_to(RECIPIENTS) == []
    assert len(world.emails_to(MAINTAINERS)) == 1


def test_both_validators_fail_excludes_item_and_retries_next_run(world, capsys):
    world.hits[Q1] = [hit(1)]
    world.jev[url(1)] = FakeResponse(503)
    world.fallback[url(1)] = FakeResponse(500)
    assert run.main() == 0
    assert stored(1).id not in world.seen()
    assert url(1) not in world.readme()
    (alert,) = world.emails_to(MAINTAINERS)
    assert "type: validation (excluded)" in alert["body"]
    assert "excluded=1" in capsys.readouterr().out

    world.jev[url(1)] = 0.9
    world.sent.clear()
    assert run.main() == 0
    assert world.seen()[stored(1).id]["verdict"] == "genuine"
    assert url(1) in world.readme()


def test_new_opportunity_email_failure_keeps_items_pending_and_alerts(world, capsys):
    world.hits[Q1] = [hit(1)]
    world.failing_subjects = ["nova(s) oportunidade(s)"]
    assert run.main() == 0
    assert world.seen()[stored(1).id]["notified"] is False
    assert url(1) in world.readme()
    (alert,) = world.emails_to(MAINTAINERS)
    assert "type: email" in alert["body"]
    assert "new-opportunity email to 2 recipient(s)" in alert["body"]
    assert_no_address(capsys)


def test_failure_and_new_items_send_two_separate_emails(world):
    world.hits[Q1] = [hit(1)]
    world.hits[Q2] = RatelimitException("202 Ratelimit")
    assert run.main() == 0
    assert [m["to"] for m in world.sent] == [RECIPIENTS, MAINTAINERS]


def test_unexpected_exception_sends_report_prints_summary_and_raises(world, capsys):
    world.hits[Q1] = [hit(1)]
    (world.root / "README.md").write_text("no markers here\n")
    with pytest.raises(report.ReportError):
        run.main()
    (alert,) = world.emails_to(MAINTAINERS)
    assert "type: unexpected" in alert["body"] and "ReportError" in alert["body"]
    text = assert_no_address(capsys)
    assert "partial summary: queries_run=2 candidates_found=1" in text


def test_missing_secret_raises_before_any_email(world, monkeypatch):
    monkeypatch.delenv("GMAIL_APP_PASSWORD")
    world.hits[Q1] = [hit(1)]
    with pytest.raises(config.ConfigError):
        run.main()
    assert world.sent == []
    assert world.jev_urls == []


def test_module_exit_code_is_non_zero_when_a_secret_is_missing(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in run.REQUIRED_SECRETS}
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    proc = subprocess.run(
        [sys.executable, "-m", "opportunity_watch.run"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "OPENROUTER_API_KEY" in proc.stderr


def test_empty_recipient_list_updates_readme_and_keeps_items_pending(world, monkeypatch, capsys):
    monkeypatch.setenv("OPPORTUNITY_RECIPIENTS", "")
    world.hits[Q1] = [hit(1)]
    assert run.main() == 0
    assert url(1) in world.readme()
    assert world.seen()[stored(1).id]["notified"] is False
    assert world.sent == []
    assert "warning: recipient list is empty" in capsys.readouterr().out

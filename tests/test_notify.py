import smtplib

import pytest

from opportunity_watch import notify
from opportunity_watch.models import Candidate, FailureRecord

SENDER = "watcher.bot@gmail.com"
RECIPIENTS = ["ana@example.com", "bruno@example.org"]


def make(id_):
    return Candidate(
        id=id_,
        title=f"Edital {id_}",
        url=f"https://ifpr.edu.br/{id_}",
        source_site="ifpr.edu.br",
        first_seen="2026-10-08",
        last_seen="2026-10-08",
        miss_count=0,
        verdict="genuine",
        notified=False,
    )


@pytest.fixture
def smtp(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", SENDER)
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-pass")
    sent, state = [], {"error": None}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert (host, port) == ("smtp.gmail.com", 465)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def login(self, user, password):
            assert (user, password) == (SENDER, "app-pass")

        def send_message(self, message, from_addr, to_addrs):
            if state["error"]:
                raise state["error"]
            sent.append({"message": message, "from": from_addr, "to": list(to_addrs)})

    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    return sent, state


def assert_no_address(text):
    assert all(address not in text for address in [*RECIPIENTS, "@example"])


# T14: _send


def test_send_puts_recipients_only_in_the_envelope(smtp):
    sent, _ = smtp
    notify._send("subject", "body", RECIPIENTS)
    (mail,) = sent
    assert mail["message"]["To"] == SENDER
    assert mail["message"]["From"] == SENDER
    assert mail["to"] == RECIPIENTS
    headers = "".join(f"{k}: {v}\n" for k, v in mail["message"].items())
    assert_no_address(headers)


def test_smtp_error_raises_send_error_without_addresses(smtp, capsys):
    _, state = smtp
    state["error"] = smtplib.SMTPRecipientsRefused({RECIPIENTS[0]: (550, b"no such user")})
    with pytest.raises(notify.SendError) as exc:
        notify._send("subject", "body", RECIPIENTS)
    assert str(exc.value) == "SMTPRecipientsRefused"
    assert exc.value.__cause__ is None
    captured = capsys.readouterr()
    assert_no_address(captured.out + captured.err)


# T15: send_new_opportunities and send_failure_report


def test_new_opportunities_email_lists_only_given_items(smtp):
    sent, _ = smtp
    result = notify.send_new_opportunities([make("a"), make("b")], RECIPIENTS)
    assert result == notify.NotifyResult(sent_to=2, skipped=False, failure=None)
    (mail,) = sent
    body = mail["message"].get_content()
    assert "https://ifpr.edu.br/a" in body and "https://ifpr.edu.br/b" in body
    assert body.count("https://") == 2
    assert mail["to"] == RECIPIENTS


@pytest.mark.parametrize(("items", "recipients"), [([], RECIPIENTS), ([make("a")], [])])
def test_no_items_or_no_recipients_sends_nothing_and_is_not_a_failure(smtp, items, recipients):
    sent, _ = smtp
    result = notify.send_new_opportunities(items, recipients)
    assert result == notify.NotifyResult(sent_to=0, skipped=True, failure=None)
    assert sent == []


def test_failure_report_lists_type_target_and_message(smtp):
    sent, _ = smtp
    failures = [
        FailureRecord(
            "search", "site:a.br x", "RatelimitException: 202", "2026-10-08T11:00:00+00:00"
        ),
        FailureRecord(
            "validation", "https://a.br/1", "Jev failed", "2026-10-08T11:01:00+00:00", True
        ),
    ]
    result = notify.send_failure_report(failures, ["ops@example.com"])
    assert result == notify.NotifyResult(sent_to=1, skipped=False, failure=None)
    body = sent[0]["message"].get_content()
    for f in failures:
        assert f"type: {f.type}" in body
        assert f"target: {f.target}" in body
        assert f"error: {f.message}" in body
    assert "type: validation (excluded)" in body
    assert sent[0]["message"]["To"] == SENDER


@pytest.mark.parametrize(
    ("failures", "maintainers"),
    [([], ["ops@example.com"]), ([FailureRecord("search", "q", "e", "t")], [])],
)
def test_failure_report_skips_without_failures_or_maintainers(smtp, failures, maintainers):
    sent, _ = smtp
    result = notify.send_failure_report(failures, maintainers)
    assert result == notify.NotifyResult(sent_to=0, skipped=True, failure=None)
    assert sent == []


def test_send_error_is_returned_as_failure_without_address(smtp, capsys):
    _, state = smtp
    state["error"] = smtplib.SMTPAuthenticationError(535, b"bad credentials")
    result = notify.send_new_opportunities([make("a")], RECIPIENTS)
    assert (result.sent_to, result.skipped) == (0, False)
    assert (result.failure.type, result.failure.target, result.failure.message) == (
        "email",
        "new-opportunity email to 2 recipient(s)",
        "SMTPAuthenticationError",
    )
    captured = capsys.readouterr()
    assert_no_address(f"{result.failure}{captured.out}{captured.err}")

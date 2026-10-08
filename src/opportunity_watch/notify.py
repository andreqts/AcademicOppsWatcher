import smtplib
from email.message import EmailMessage

from opportunity_watch import config
from opportunity_watch.models import Candidate, FailureRecord, NotifyResult, utc_timestamp

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SUBJECT_PREFIX = "[AcademicOppsWatcher]"


class SendError(Exception):
    pass


def _send(subject: str, body: str, bcc_list: list[str]) -> None:
    sender = config.require_env("GMAIL_ADDRESS")
    password = config.require_env("GMAIL_APP_PASSWORD")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = sender
    message.set_content(body)
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.login(sender, password)
            # invariant: recipients only in the envelope, never in a header (Bcc, P1-AC10).
            smtp.send_message(message, from_addr=sender, to_addrs=bcc_list)
    except (smtplib.SMTPException, OSError) as e:
        # hazard: SMTP errors such as SMTPRecipientsRefused embed addresses, so keep only the type.
        raise SendError(type(e).__name__) from None


def _deliver(subject: str, body: str, addresses: list[str], what: str) -> NotifyResult:
    try:
        _send(subject, body, addresses)
    except SendError as e:
        failure = FailureRecord(
            type="email",
            target=f"{what} to {len(addresses)} recipient(s)",
            message=str(e),
            timestamp=utc_timestamp(),
        )
        return NotifyResult(sent_to=0, skipped=False, failure=failure)
    return NotifyResult(sent_to=len(addresses), skipped=False, failure=None)


def send_new_opportunities(new_items: list[Candidate], recipients: list[str]) -> NotifyResult:
    if not new_items:
        return NotifyResult(sent_to=0, skipped=True, failure=None)
    if not recipients:
        print(f"warning: recipient list is empty; {len(new_items)} opportunities stay pending")
        return NotifyResult(sent_to=0, skipped=True, failure=None)
    lines = [
        f"- {c.title}\n  {c.url}\n  ({c.source_site}, visto desde {c.first_seen})"
        for c in new_items
    ]
    body = "Novas oportunidades encontradas:\n\n" + "\n\n".join(lines) + "\n"
    subject = f"{SUBJECT_PREFIX} {len(new_items)} nova(s) oportunidade(s)"
    return _deliver(subject, body, recipients, "new-opportunity email")


def send_failure_report(failures: list[FailureRecord], maintainer_list: list[str]) -> NotifyResult:
    if not failures:
        return NotifyResult(sent_to=0, skipped=True, failure=None)
    if not maintainer_list:
        print(
            f"warning: maintainer list is empty; failure report with {len(failures)} items skipped"
        )
        return NotifyResult(sent_to=0, skipped=True, failure=None)
    lines = [
        f"- type: {f.type}{' (excluded)' if f.excluded else ''}\n"
        f"  target: {f.target}\n  error: {f.message}\n  at: {f.timestamp}"
        for f in failures
    ]
    body = "Falhas registradas nesta execução:\n\n" + "\n\n".join(lines) + "\n"
    subject = f"{SUBJECT_PREFIX} relatório de falhas: {len(failures)}"
    return _deliver(subject, body, maintainer_list, "failure report")

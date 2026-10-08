import pytest
import requests

from opportunity_watch import validate
from opportunity_watch.models import Candidate

CANDIDATE = Candidate(
    id="abc",
    title="Edital PSS Engenharia Elétrica",
    url="https://unila.edu.br/editais/7",
    source_site="unila.edu.br",
    first_seen="2026-10-08",
    last_seen="2026-10-08",
    miss_count=0,
    verdict="genuine",
    notified=False,
)

SNIPPET = "Processo seletivo para professor substituto em Engenharia Elétrica, Foz do Iguaçu."

P1_AC20_QUESTION = (
    "Esta é uma oportunidade de concurso com vagas para professor efetivo ou temporário "
    "(PSS ou Substituto), nas áreas de Computação (Engenharia da Computação ou Ciência da "
    "Computação ou afins), Engenharia Elétrica, Engenharia de Energia, para atuação da cidade "
    "de Foz do Iguaçu/PR?"
)


class FakeResponse:
    def __init__(self, status=200, body=None, raw=None):
        self.status_code, self._body, self._raw = status, body, raw

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        if self._raw is not None:
            raise requests.exceptions.JSONDecodeError("Expecting value", self._raw, 0)
        return self._body


@pytest.fixture
def posts(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    calls, replies = [], {}

    def fake_post(url, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers})
        reply = replies[url]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(validate.requests, "post", fake_post)
    return calls, replies


def jev_reply(p):
    return FakeResponse(body={"answers": {"genuine": {"type": "noul", "noul": p}}})


def chat_reply(text):
    return FakeResponse(body={"choices": [{"message": {"content": text}}]})


# T10: _call_jev


def test_jev_request_uses_verified_endpoint_question_and_configured_model(posts, monkeypatch):
    calls, replies = posts
    monkeypatch.setenv("JEV_MODEL", "typesafe/jev-override-test")
    replies[validate.DECISIONS_URL] = jev_reply(0.9)
    validate._call_jev(CANDIDATE, SNIPPET)
    (call,) = calls
    assert call["url"] == "https://openrouter.ai/api/alpha/decisions"
    assert call["headers"]["Authorization"] == "Bearer sk-test"
    assert call["json"]["model"] == "typesafe/jev-override-test"
    question = call["json"]["questions"]["genuine"]
    assert question["type"] == "noul"
    assert question["instructions"] == P1_AC20_QUESTION
    assert set(question["criteria"]) == {"true", "false"}
    assert call["json"]["state"]["url"] == CANDIDATE.url
    assert call["json"]["state"]["snippet"] == SNIPPET


def test_jev_probability_above_threshold_is_genuine(posts):
    posts[1][validate.DECISIONS_URL] = jev_reply(0.51)
    assert validate._call_jev(CANDIDATE, SNIPPET) == validate.JevAnswer(
        genuine=True, probability=0.51
    )


def test_jev_probability_exactly_at_threshold_is_genuine(posts):
    posts[1][validate.DECISIONS_URL] = jev_reply(0.5)
    assert validate._call_jev(CANDIDATE, SNIPPET) == validate.JevAnswer(
        genuine=True, probability=0.5
    )


def test_jev_probability_below_threshold_is_false_positive(posts):
    posts[1][validate.DECISIONS_URL] = jev_reply(0.49)
    assert validate._call_jev(CANDIDATE, SNIPPET) == validate.JevAnswer(
        genuine=False, probability=0.49
    )


@pytest.mark.parametrize(
    "reply",
    [
        FakeResponse(status=503),
        requests.Timeout("read timed out"),
        FakeResponse(raw="<html>"),
        FakeResponse(body={"answers": {}}),
    ],
    ids=["http-error", "timeout", "malformed-json", "missing-answer"],
)
def test_jev_failures_raise_jev_call_error(posts, reply):
    posts[1][validate.DECISIONS_URL] = reply
    with pytest.raises(validate.JevCallError):
        validate._call_jev(CANDIDATE, SNIPPET)


# T11: _call_free_fallback


def test_fallback_uses_exactly_openrouter_free(posts):
    calls, replies = posts
    replies[validate.CHAT_URL] = chat_reply("Sim.")
    validate._call_free_fallback(CANDIDATE, SNIPPET)
    (call,) = calls
    assert call["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert call["json"]["model"] == "openrouter/free"
    assert P1_AC20_QUESTION in call["json"]["messages"][0]["content"]
    assert SNIPPET in call["json"]["messages"][0]["content"]


@pytest.mark.parametrize(
    ("text", "genuine"), [("Sim.", True), ("  sim", True), ("Não", False), ("nao, não é", False)]
)
def test_fallback_parses_yes_no(posts, text, genuine):
    posts[1][validate.CHAT_URL] = chat_reply(text)
    assert validate._call_free_fallback(CANDIDATE, SNIPPET) == validate.FallbackAnswer(
        genuine=genuine
    )


@pytest.mark.parametrize(
    "reply",
    [
        FakeResponse(status=500),
        requests.Timeout("read timed out"),
        chat_reply("Talvez"),
        chat_reply("simulação"),
        FakeResponse(body={"choices": []}),
    ],
    ids=["http-error", "timeout", "unusable-answer", "not-a-yes", "no-choices"],
)
def test_fallback_failures_raise_validation_failed(posts, reply):
    posts[1][validate.CHAT_URL] = reply
    with pytest.raises(validate.ValidationFailed):
        validate._call_free_fallback(CANDIDATE, SNIPPET)


# T12: classify


def test_classify_jev_genuine(posts):
    posts[1][validate.DECISIONS_URL] = jev_reply(0.8)
    result, failures = validate.classify(CANDIDATE, SNIPPET)
    assert (result.candidate_id, result.verdict, result.confidence, result.method) == (
        "abc",
        "genuine",
        0.8,
        "jev",
    )
    assert failures == []


def test_classify_jev_false_positive(posts):
    posts[1][validate.DECISIONS_URL] = jev_reply(0.1)
    result, failures = validate.classify(CANDIDATE, SNIPPET)
    assert (result.verdict, result.method, failures) == ("false_positive", "jev", [])


@pytest.mark.parametrize(("text", "verdict"), [("sim", "genuine"), ("não", "false_positive")])
def test_classify_jev_fails_fallback_answers_and_degraded_failure_is_recorded(posts, text, verdict):
    _, replies = posts
    replies[validate.DECISIONS_URL] = FakeResponse(status=502)
    replies[validate.CHAT_URL] = chat_reply(text)
    result, failures = validate.classify(CANDIDATE, SNIPPET)
    assert (result.verdict, result.method) == (verdict, "free_fallback")
    assert [(f.type, f.target, f.excluded) for f in failures] == [
        ("validation", CANDIDATE.url, False)
    ]
    assert "Jev failed" in failures[0].message


def test_classify_both_fail_is_excluded(posts):
    replies = posts[1]
    replies[validate.DECISIONS_URL] = requests.Timeout("jev timeout")
    replies[validate.CHAT_URL] = FakeResponse(status=500)
    result, failures = validate.classify(CANDIDATE, SNIPPET)
    assert (result.verdict, result.method) == ("failed", "free_fallback")
    assert [(f.type, f.target, f.excluded) for f in failures] == [
        ("validation", CANDIDATE.url, True)
    ]

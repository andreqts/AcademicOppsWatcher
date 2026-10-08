import re
from dataclasses import dataclass

import requests

from opportunity_watch import config
from opportunity_watch.models import Candidate, FailureRecord, ValidationResult, utc_timestamp

# why: the Decisions API sits outside /api/v1 (verified 2026-10-08, see design.md Risks).
DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
# invariant: free-tier only; openrouter/auto can bill paid models (P1-AC6).
FALLBACK_MODEL = "openrouter/free"
GENUINE_THRESHOLD = 0.5
TIMEOUT_SECONDS = 60

QUESTION = (
    "Esta é uma oportunidade de concurso com vagas para professor efetivo ou temporário "
    "(PSS ou Substituto), nas áreas de Computação (Engenharia da Computação ou Ciência da "
    "Computação ou afins), Engenharia Elétrica, Engenharia de Energia, para atuação da cidade "
    "de Foz do Iguaçu/PR?"
)


class JevCallError(Exception):
    pass


class ValidationFailed(Exception):
    pass


@dataclass
class JevAnswer:
    genuine: bool
    probability: float


@dataclass
class FallbackAnswer:
    genuine: bool


def _state(candidate: Candidate, snippet: str) -> dict:
    return {
        "title": candidate.title,
        "url": candidate.url,
        "source_site": candidate.source_site,
        "snippet": snippet,
    }


def _post(url: str, payload: dict) -> dict:
    response = requests.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {config.require_env('OPENROUTER_API_KEY')}"},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _call_jev(candidate: Candidate, snippet: str) -> JevAnswer:
    payload = {
        "model": config.jev_model(),
        "state": _state(candidate, snippet),
        "questions": {
            "genuine": {
                "type": "noul",
                "instructions": QUESTION,
                "criteria": {
                    "true": "Sim: atende a todos os critérios da pergunta.",
                    "false": "Não: deixa de atender a pelo menos um critério da pergunta.",
                },
            }
        },
    }
    try:
        probability = float(_post(DECISIONS_URL, payload)["answers"]["genuine"]["noul"])
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        raise JevCallError(f"{type(e).__name__}: {e}") from e
    return JevAnswer(genuine=probability >= GENUINE_THRESHOLD, probability=probability)


def _call_free_fallback(candidate: Candidate, snippet: str) -> FallbackAnswer:
    state = _state(candidate, snippet)
    prompt = (
        f"{QUESTION}\n\nTítulo: {state['title']}\nURL: {state['url']}\n"
        f"Site: {state['source_site']}\nTrecho: {state['snippet']}\n\nResponda apenas 'sim' ou 'não'."
    )
    payload = {"model": FALLBACK_MODEL, "messages": [{"role": "user", "content": prompt}]}
    try:
        content = _post(CHAT_URL, payload)["choices"][0]["message"]["content"]
        match = re.match(r"\W*(sim|não|nao)\b", content.strip().lower())
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as e:
        raise ValidationFailed(f"{type(e).__name__}: {e}") from e
    if not match:
        raise ValidationFailed(f"unusable answer: {content[:80]!r}")
    return FallbackAnswer(genuine=match.group(1) == "sim")


def _verdict(genuine: bool) -> str:
    return "genuine" if genuine else "false_positive"


def classify(candidate: Candidate, snippet: str) -> tuple[ValidationResult, list[FailureRecord]]:
    try:
        jev = _call_jev(candidate, snippet)
        result = ValidationResult(candidate.id, _verdict(jev.genuine), jev.probability, "jev", None)
        return result, []
    except JevCallError as jev_error:
        jev_message = f"Jev failed: {jev_error}"
    try:
        fallback = _call_free_fallback(candidate, snippet)
    except ValidationFailed as e:
        message = f"{jev_message}; free fallback failed: {e}"
        result = ValidationResult(candidate.id, "failed", None, "free_fallback", message)
        return result, [_validation_failure(candidate, message, excluded=True)]
    result = ValidationResult(
        candidate.id, _verdict(fallback.genuine), None, "free_fallback", jev_message
    )
    return result, [_validation_failure(candidate, jev_message, excluded=False)]


def _validation_failure(candidate: Candidate, message: str, excluded: bool) -> FailureRecord:
    return FailureRecord(
        type="validation",
        target=candidate.url,
        message=message,
        timestamp=utc_timestamp(),
        excluded=excluded,
    )

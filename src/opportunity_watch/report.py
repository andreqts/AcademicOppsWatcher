from opportunity_watch.models import Candidate

START_MARKER = "<!-- OPPORTUNITIES:START -->"
END_MARKER = "<!-- OPPORTUNITIES:END -->"
EMPTY_LINE = "_Nenhuma oportunidade aberta no momento._"


class ReportError(Exception):
    pass


def _escape(text: str) -> str:
    return text.replace("[", r"\[").replace("]", r"\]")


def render_section(open_opportunities: list[Candidate]) -> str:
    if not open_opportunities:
        return EMPTY_LINE
    # why: a stable order keeps README byte-identical between runs with the same set (P1-AC15).
    ordered = sorted(open_opportunities, key=lambda c: (c.first_seen, c.title, c.id), reverse=True)
    return "\n".join(
        f"- [{_escape(c.title)}]({c.url}) - {c.source_site}, visto desde {c.first_seen}"
        for c in ordered
    )


def update_readme(path: str, rendered: str) -> bool:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if text.count(START_MARKER) != 1 or text.count(END_MARKER) != 1:
        raise ReportError(f"{path} must contain {START_MARKER} and {END_MARKER} exactly once")
    before, rest = text.split(START_MARKER)
    if END_MARKER in before:
        raise ReportError(f"{END_MARKER} comes before {START_MARKER} in {path}")
    _, after = rest.split(END_MARKER)
    new_text = f"{before}{START_MARKER}\n{rendered}\n{END_MARKER}{after}"
    if new_text == text:
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_text)
    return True

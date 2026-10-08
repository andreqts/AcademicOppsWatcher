import pytest

from opportunity_watch import report
from opportunity_watch.models import Candidate

OUTSIDE_BEFORE = "# Title\n\nIntro text.\n\n"
OUTSIDE_AFTER = "\n\n## Footer\nkeep me\n"


def make(id_, title, first_seen):
    return Candidate(
        id=id_,
        title=title,
        url=f"https://unila.edu.br/{id_}",
        source_site="unila.edu.br",
        first_seen=first_seen,
        last_seen=first_seen,
        miss_count=0,
        verdict="genuine",
        notified=False,
    )


def readme(tmp_path, inner="old content"):
    path = tmp_path / "README.md"
    path.write_text(
        f"{OUTSIDE_BEFORE}{report.START_MARKER}\n{inner}\n{report.END_MARKER}{OUTSIDE_AFTER}"
    )
    return path


def test_render_lists_each_open_opportunity_newest_first():
    rendered = report.render_section(
        [make("a", "Edital [PSS] 1", "2026-10-01"), make("b", "Edital 2", "2026-10-05")]
    )
    assert rendered == (
        "- [Edital 2](https://unila.edu.br/b) - unila.edu.br, visto desde 2026-10-05\n"
        r"- [Edital \[PSS\] 1](https://unila.edu.br/a) - unila.edu.br, visto desde 2026-10-01"
    )


def test_empty_set_renders_explicit_no_open_opportunities_line():
    assert report.render_section([]) == "_Nenhuma oportunidade aberta no momento._"


def test_only_text_between_markers_changes(tmp_path):
    path = readme(tmp_path)
    assert report.update_readme(str(path), "- new line") is True
    assert path.read_text() == (
        f"{OUTSIDE_BEFORE}{report.START_MARKER}\n- new line\n{report.END_MARKER}{OUTSIDE_AFTER}"
    )


def test_unchanged_input_returns_false_and_keeps_file(tmp_path):
    path = readme(tmp_path, inner="- same")
    before = path.read_bytes()
    assert report.update_readme(str(path), "- same") is False
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "text",
    [
        "no markers at all\n",
        f"{report.START_MARKER}\nonly start\n",
        f"{report.START_MARKER}\n{report.END_MARKER}\n{report.START_MARKER}\n{report.END_MARKER}\n",
        f"{report.END_MARKER}\nreversed\n{report.START_MARKER}\n",
    ],
    ids=["missing", "no-end", "duplicated", "reversed"],
)
def test_bad_markers_raise_report_error(tmp_path, text):
    path = tmp_path / "README.md"
    path.write_text(text)
    with pytest.raises(report.ReportError):
        report.update_readme(str(path), "- x")
    assert path.read_text() == text

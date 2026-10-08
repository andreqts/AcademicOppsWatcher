from pathlib import Path

import pytest
import yaml

from opportunity_watch import config


def test_require_env_returns_value(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "bot@example.com")
    assert config.require_env("GMAIL_ADDRESS") == "bot@example.com"


def test_require_env_missing_raises_naming_the_variable(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(config.ConfigError) as exc:
        config.require_env("OPENROUTER_API_KEY")
    assert "OPENROUTER_API_KEY" in str(exc.value)


def test_require_env_blank_counts_as_missing_and_hides_value(monkeypatch):
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "  \t ")
    with pytest.raises(config.ConfigError) as exc:
        config.require_env("GMAIL_APP_PASSWORD")
    assert str(exc.value) == "required environment variable GMAIL_APP_PASSWORD is not set"


def test_load_address_list_strips_blanks_and_whitespace(monkeypatch):
    monkeypatch.setenv("OPPORTUNITY_RECIPIENTS", "\n a@example.com \n\n  \nb@example.com\n")
    assert config.load_address_list("OPPORTUNITY_RECIPIENTS") == ["a@example.com", "b@example.com"]


def test_load_address_list_unset_returns_empty(monkeypatch):
    monkeypatch.delenv("MAINTAINER_ALERTS", raising=False)
    assert config.load_address_list("MAINTAINER_ALERTS") == []


def test_load_queries_reads_queries_key(tmp_path):
    path = tmp_path / "queries.yaml"
    path.write_text("queries:\n  # comment\n  - 'site:a.br \"x\"'\n  - 'site:b.br y'\n")
    assert config.load_queries(str(path)) == ['site:a.br "x"', "site:b.br y"]


def test_load_queries_malformed_yaml_raises(tmp_path):
    path = tmp_path / "queries.yaml"
    path.write_text("queries: [unclosed\n")
    with pytest.raises(yaml.YAMLError):
        config.load_queries(str(path))


def test_jev_model_default(monkeypatch):
    monkeypatch.delenv("JEV_MODEL", raising=False)
    assert config.jev_model() == "~typesafe/jev-latest"


def test_jev_model_override(monkeypatch):
    monkeypatch.setenv("JEV_MODEL", "typesafe/jev-1.13")
    assert config.jev_model() == "typesafe/jev-1.13"


def test_shipped_queries_file_is_valid():
    path = Path(__file__).resolve().parents[1] / "config" / "queries.yaml"
    queries = config.load_queries(str(path))
    assert len(queries) == 8
    assert all(q.startswith("site:") for q in queries)

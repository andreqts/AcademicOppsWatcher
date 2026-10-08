import os

import yaml

DEFAULT_JEV_MODEL = "~typesafe/jev-latest"


class ConfigError(Exception):
    pass


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        # invariant: names the variable only, never a value (AD-001).
        raise ConfigError(f"required environment variable {name} is not set")
    return value


def load_address_list(env_var: str) -> list[str]:
    return [line.strip() for line in os.environ.get(env_var, "").splitlines() if line.strip()]


def load_queries(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["queries"]


def jev_model() -> str:
    return os.environ.get("JEV_MODEL", "").strip() or DEFAULT_JEV_MODEL

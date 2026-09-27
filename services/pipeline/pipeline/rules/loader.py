"""Load the YAML ruleset."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from pipeline.rules.models import RuleConfig

RULES_PATH = Path(__file__).resolve().parent / "rules.yaml"


@lru_cache(maxsize=4)
def _load_from(path_str: str) -> RuleConfig:
    raw = yaml.safe_load(Path(path_str).read_text(encoding="utf-8"))
    return RuleConfig.model_validate(raw)


def load_rule_config(path: str | Path | None = None) -> RuleConfig:
    """Read rules.yaml (safe_load only; no code execution) into a validated model."""
    return _load_from(str(Path(path) if path is not None else RULES_PATH))

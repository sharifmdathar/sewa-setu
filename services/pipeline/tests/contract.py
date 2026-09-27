"""Dependency-free validator for the subset of OpenAPI that the frozen contract uses.

`shared/contracts/openapi.yaml` is the only truth between the tracks, so the pipeline's own
output is checked against that file rather than against a hand-written expectation. A
validation library is not worth a new dependency for the handful of keywords the contract
actually uses: `type`, `required`, `properties`, `items`, `enum`, `$ref`, `minimum`,
`maximum` and `format: date-time`.

The contract never sets `additionalProperties: false`, so an undeclared key is technically
allowed by it. We reject one anyway wherever `properties` is declared: that is the
field-for-field match the tracks need, and it is what catches a snake_case leak onto the wire.
"""

from __future__ import annotations

import datetime as dt
import functools
from pathlib import Path
from typing import Any

import yaml

CONTRACT_PATH = Path(__file__).resolve().parents[3] / "shared" / "contracts" / "openapi.yaml"


@functools.lru_cache(maxsize=1)
def _document() -> dict[str, Any]:
    loaded = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def schema(name: str) -> dict[str, Any]:
    """One component schema, e.g. `schema("ScrutinyReport")`."""
    components: dict[str, Any] = _document()["components"]["schemas"]
    if name not in components:
        raise KeyError(f"{name} is not a components/schemas entry of {CONTRACT_PATH}")
    return components[name]


def validate(instance: Any, name: str) -> list[str]:
    """Contract violations as readable paths; an empty list means the instance conforms."""
    return _validate(instance, schema(name), "$")


def assert_valid(instance: Any, name: str) -> None:
    problems = validate(instance, name)
    if problems:
        raise AssertionError(
            f"{name} does not conform to {CONTRACT_PATH.name}:\n  " + "\n  ".join(problems)
        )


def _resolve(ref: str) -> dict[str, Any]:
    node: Any = _document()
    for part in ref.removeprefix("#/").split("/"):
        node = node[part]
    result: dict[str, Any] = node
    return result


def _validate(value: Any, node: dict[str, Any], path: str) -> list[str]:
    if "$ref" in node:
        return _validate(value, _resolve(node["$ref"]), path)

    declared = node.get("type")
    if declared is not None and not _type_matches(value, declared):
        return [f"{path}: expected {declared}, got {type(value).__name__}"]

    problems: list[str] = []
    if declared == "object":
        problems += _validate_object(value, node, path)
    elif declared == "array":
        problems += _validate_array(value, node, path)
    elif declared == "string":
        problems += _validate_string(value, node, path)
    if declared in {"integer", "number"}:
        problems += _validate_range(value, node, path)
    if "enum" in node and value not in node["enum"]:
        problems.append(f"{path}: {value!r} is not one of {node['enum']}")
    return problems


def _validate_object(value: dict[str, Any], node: dict[str, Any], path: str) -> list[str]:
    problems = [
        f"{path}.{name}: required by the contract, missing from the payload"
        for name in node.get("required", ())
        if name not in value
    ]
    properties: dict[str, Any] = node.get("properties") or {}
    if not properties:
        return problems
    problems += [
        f"{path}.{key}: not declared by the contract"
        for key in value
        if key not in properties
    ]
    for key, sub_node in properties.items():
        if key in value:
            problems += _validate(value[key], sub_node, f"{path}.{key}")
    return problems


def _validate_array(value: list[Any], node: dict[str, Any], path: str) -> list[str]:
    items = node.get("items")
    if items is None:
        return []
    problems: list[str] = []
    for index, element in enumerate(value):
        problems += _validate(element, items, f"{path}[{index}]")
    return problems


def _validate_string(value: str, node: dict[str, Any], path: str) -> list[str]:
    if node.get("format") != "date-time":
        return []
    if _is_date_time(value):
        return []
    return [f"{path}: '{value}' is not an RFC 3339 date-time with an offset"]


def _validate_range(value: int | float, node: dict[str, Any], path: str) -> list[str]:
    problems: list[str] = []
    if "minimum" in node and value < node["minimum"]:
        problems.append(f"{path}: {value} is below minimum {node['minimum']}")
    if "maximum" in node and value > node["maximum"]:
        problems.append(f"{path}: {value} is above maximum {node['maximum']}")
    return problems


def _is_date_time(raw: str) -> bool:
    text = f"{raw[:-1]}+00:00" if raw[-1:] in {"Z", "z"} else raw
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _type_matches(value: Any, declared: str) -> bool:
    if declared == "object":
        return isinstance(value, dict)
    if declared == "array":
        return isinstance(value, list)
    if declared == "string":
        return isinstance(value, str)
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True

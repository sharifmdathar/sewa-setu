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
import os
from pathlib import Path
from typing import Any

import yaml

# `SEWA_CONTRACT` points the validator at a different YAML. It exists so a proposed
# change-request can be validated against the real test suite before anyone edits the
# frozen contract; unset, it reads shared/contracts/openapi.yaml and nothing changes.
CONTRACT_PATH = Path(
    os.environ.get("SEWA_CONTRACT")
    or Path(__file__).resolve().parents[3] / "shared" / "contracts" / "openapi.yaml"
)


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


def response_schema(method: str, path: str, status: str) -> dict[str, Any]:
    """The schema a path declares inline for one status, e.g. `("get", "/services", "200")`.

    Several contract responses have no named component - `/services` and `/officer/queue` are
    bare arrays, and `/officer/decisions` returns an inline object - so path-level lookup is
    what lets those be checked field-for-field too.
    """
    # The media-type key is literally "application/json"; a JSON pointer escapes its slash as ~1
    # (so "~1json", not "~1/json", which would still be a separator).
    pointer = (
        f"#/paths/{path.replace('/', '~1')}/{method.lower()}"
        f"/responses/{status}/content/application~1json/schema"
    )
    return _resolve(pointer)


def assert_valid_response(instance: Any, method: str, path: str, status: str) -> Any:
    """Validate a live response against what its own contract path declares; return it."""
    try:
        node = response_schema(method, path, status)
    except (KeyError, TypeError):
        name = f"{method.upper()} {path} {status}"
        raise AssertionError(
            f"{CONTRACT_PATH.name} declares no JSON response for {name}"
        ) from None  # the lookup error is noise; the absence is the finding
    problems = _validate(instance, node, "$")
    if problems:
        raise AssertionError(
            f"{method.upper()} {path} ({status}) does not conform to the contract:\n  "
            + "\n  ".join(problems)
        )
    return instance


def contract_paths() -> dict[str, Any]:
    """Every path the contract declares, so a test can prove none of them went unjudged."""
    paths: dict[str, Any] = _document()["paths"]
    return paths


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
        node = node[part.replace("~1", "/").replace("~0", "~")]
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
    fmt = node.get("format")
    if fmt == "date-time" and not _is_date_time(value):
        return [f"{path}: '{value}' is not an RFC 3339 date-time with an offset"]
    if fmt == "date" and not _is_date(value):
        return [f"{path}: '{value}' is not an ISO calendar date"]
    return []


def _is_date(raw: str) -> bool:
    try:
        dt.date.fromisoformat(raw)
    except ValueError:
        return False
    return True


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

"""The contract's own inventory, with no server involved.

Every path the frozen file declares must be judged by the conformance suite, and every path this
suite claims to judge must still exist in the file. A change request that adds a route therefore
breaks a test instead of going quietly untested.
"""

from __future__ import annotations

from contract import contract_paths, response_schema

#: (method, contract path) pairs this module judges; {id} is filled by the fixtures above.
COVERED = {
    ("get", "/healthz"),
    ("get", "/services"),
    ("post", "/applications"),
    ("get", "/applications/{id}"),
    ("post", "/applications/{id}/documents"),
    ("get", "/applications/{id}/documents"),
    ("post", "/applications/{id}/scrutiny/run"),
    ("get", "/applications/{id}/scrutiny"),
    ("get", "/officer/queue"),
    ("post", "/officer/decisions"),
    ("get", "/metrics/summary"),
}


def _success_status(method: str, path: str) -> str:
    responses = contract_paths()[path][method]["responses"]
    return next(str(code) for code in responses if str(code).startswith("2"))


def test_no_contract_path_goes_unjudged() -> None:
    """A path added to the contract without a test here must fail this, not pass silently."""
    declared = {
        (method, path)
        for path, operations in contract_paths().items()
        for method in operations
        if method in {"get", "post", "put", "patch", "delete"}
    }

    untested = declared - COVERED
    vanished = COVERED - declared
    assert not untested, f"contract paths with no live test - add one each: {sorted(untested)}"
    assert not vanished, f"tests judge paths no longer in the contract: {sorted(vanished)}"
    for method, path in sorted(COVERED - {("get", "/healthz")}):
        status = _success_status(method, path)
        assert isinstance(response_schema(method, path, status), dict), (method, path, status)

"""Inventory of every API route: each one that touches a profile, or changes anything, must go through the
ownership / session dependencies. A new endpoint that forgets them fails this test."""
from fastapi.routing import APIRoute

from app.auth import current_account, profile_reader, profile_writer
from app.main import app

# Profile-scoped POST/DELETE routes that run read-only computations or only touch the caller's OWN records
# (chat history and reports are stored per account). They need a session + CSRF + read access, not write access.
READ_ACCESS_POSTS = {
    ("POST", "/api/profiles/{internal_id}/analyze"),     # recomputes derived results; source data untouched
    ("POST", "/api/profiles/{internal_id}/fire"),        # what-if calculation, nothing stored
    ("POST", "/api/profiles/{internal_id}/decision"),    # what-if calculation, nothing stored
    ("POST", "/api/profiles/{internal_id}/payoff"),      # what-if calculation, nothing stored
    ("POST", "/api/profiles/{internal_id}/chat"),        # stores the caller's own chat lines (app_user_id)
    ("POST", "/api/profiles/{internal_id}/chat/stream"), # same as /chat, streamed
    ("DELETE", "/api/profiles/{internal_id}/chat"),      # deletes only the caller's own chat lines
    ("POST", "/api/profiles/{internal_id}/plan/preview"),  # what-if scenario, nothing stored
}
# Mutating routes with no profile in the path, and why they are allowed.
NON_PROFILE_MUTATIONS = {
    ("POST", "/api/auth/register"): "public by design (rate-limited)",
    ("POST", "/api/auth/login"): "public by design (rate-limited, lockout)",
    ("POST", "/api/auth/logout"): "needs session",
    ("POST", "/api/lookup"): "needs session; opens caller's own sandbox",
    ("POST", "/api/demo/explore"): "needs session; opens caller's own sandbox",
    ("POST", "/api/profiles"): "needs session; creates a profile owned by the caller",
    ("POST", "/api/models/retrain"): "needs session; always 410 (training is a local CLI step)",
    ("POST", "/api/models/credit-risk/score"): "needs session; pure model inference on supplied inputs, nothing stored",
    ("PUT", "/api/models/anomaly-review/{item_id}"): "needs a full (non-guest) session; writes only the caller's own review label",
    ("POST", "/api/tax/compare"): "pure calculation, no data",
    ("POST", "/api/categorise"): "pure model inference on supplied text, no data",
}
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _deps(route: APIRoute) -> set:
    out, stack = set(), [route.dependant]
    while stack:
        d = stack.pop()
        if d.call:
            out.add(d.call)
        stack.extend(d.dependencies)
    return out


def _api_routes(routes):
    """Walk the router tree. FastAPI >= 0.16x wraps included routers (`original_router`), so a flat walk of
    app.routes would see no API routes at all - and every check below would pass vacuously."""
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        inner = getattr(r, "original_router", None) or getattr(r, "routes", None)
        if inner is not None and not isinstance(r, APIRoute):
            yield from _api_routes(inner.routes if hasattr(inner, "routes") else inner)


def _routes():
    for r in _api_routes(app.routes):
        for m in r.methods:
            yield m, r.path, r


def test_route_walker_sees_the_whole_api():
    paths = {p for _, p, _ in _routes()}
    assert len(paths) >= 30 and "/api/profiles/{internal_id}/upload" in paths and "/api/auth/login" in paths


def test_every_profile_route_checks_ownership():
    n = 0
    for method, path, r in _routes():
        if "{internal_id}" not in path:
            continue
        n += 1
        deps = _deps(r)
        assert profile_reader in deps or profile_writer in deps, f"{method} {path} has no ownership check"
    assert n >= 25


def test_every_profile_mutation_requires_write_access_unless_listed():
    checked = 0
    for method, path, r in _routes():
        if method not in MUTATING or "{internal_id}" not in path:
            continue
        checked += 1
        deps = _deps(r)
        if (method, path) in READ_ACCESS_POSTS:
            assert profile_reader in deps, f"{method} {path}"
        else:
            assert profile_writer in deps, f"{method} {path} mutates a profile without profile_writer"
    assert checked >= 10


def test_every_other_mutation_is_known_and_authenticated():
    public = {("POST", "/api/auth/register"), ("POST", "/api/auth/login"), ("POST", "/api/tax/compare"), ("POST", "/api/categorise")}
    for method, path, r in _routes():
        if method not in MUTATING or "{internal_id}" in path:
            continue
        assert (method, path) in NON_PROFILE_MUTATIONS, f"unreviewed mutating route {method} {path}"
        if (method, path) not in public:
            assert current_account in _deps(r), f"{method} {path} does not require a session"

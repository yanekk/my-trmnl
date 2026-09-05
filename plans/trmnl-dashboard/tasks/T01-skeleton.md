# T01 — Project skeleton, Docker, test harness, module boundary

**Phase:** 1 · **Depends on:** T00 · **Weight:** light

## Goal

Stand up the empty project the rest of the plan fills in: the package layout that encodes the
core/adapters/render/server boundary, the Docker image and the one test command, and the guard
test that keeps the pure core pure. Getting the boundary and its guard in place first means
every later task is built inside a structure that already enforces the one architectural rule
the whole design rests on.

## Design sections this implements

DESIGN.md §3.1 (the boundary and its guard test), §5 (environment, the test command, Python
3.12 in Docker, dependency policy).

## Files

- `pyproject.toml` (or equivalent) pinning Python 3.12, `pytest`, `Pillow`, an HTTP client.
- `Dockerfile`, `docker-compose.yml` with a `test` service running `python -m pytest -q --color=no`.
- Package skeleton: `trmnl/core/`, `trmnl/adapters/`, `trmnl/render/`, `trmnl/server/`, each an
  empty package with a docstring naming its side of the boundary.
- `tests/test_boundary.py` — the guard test.
- `tests/` layout and a trivial passing test so the command is green from day one.

## Interface

The guard test scans every module under `trmnl/core/` and fails if any imports a forbidden
name:

```python
# tests/test_boundary.py
FORBIDDEN = ("requests", "httpx", "PIL", "socket", "urllib")   # plus: no datetime.now / time.time
# For each .py under trmnl/core/: parse the AST, assert no import of FORBIDDEN,
# and assert no call to datetime.datetime.now / datetime.datetime.today / time.time.
```

The message on failure says: move the code out of `core/`; do not edit this test.

## Tests

- [ ] The boundary test passes on the empty core and fails when a `core/` module imports `httpx`
      (prove it by a temporary import, then remove).
- [ ] The boundary test fails when a `core/` module calls `datetime.now()`.
- [ ] `docker compose run --rm test` exits 0 and prints a quiet summary, no ANSI colour codes.

## Done when

- [ ] `docker compose run --rm test` runs the suite quietly and green inside the 3.12 image.
- [ ] The four packages exist with the boundary guard test in place and proven to bite.
- [ ] `README` or a make target names the test command so no session has to rediscover it.

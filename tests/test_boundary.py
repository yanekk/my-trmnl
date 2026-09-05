"""The boundary guard (DESIGN SS3.1).

Scans every module under trmnl/core/ and fails if the core reaches across the
boundary: a forbidden import (network / Pillow / raw sockets), a read of the
system clock, or file I/O. The core must take the current time as an argument
and return decisions; that is the one rule this whole project rests on.

If this test fails, the fix is to MOVE the offending code out of trmnl/core/
into adapters/, render/ or server/ -- never to edit or relax this test. The
value of the boundary is precisely that the core is checkable exhaustively in
milliseconds while everything across it can only be checked by a person or
against fixtures.

The check is a static AST scan, so it needs no imports to succeed and cannot be
fooled by an import guarded behind an ``if``. The synthetic-source tests below
prove the guard actually bites, which is why no real core module ever has to be
broken on purpose to demonstrate it.
"""

import ast
import pathlib

CORE_DIR = pathlib.Path(__file__).resolve().parent.parent / "trmnl" / "core"

# Top-level module names the core may never import: the network, Pillow, and the
# low-level socket/urllib machinery underneath an HTTP client. datetime, zoneinfo
# and time are deliberately NOT here -- the core is allowed to import them for
# timezone-aware formatting; what it may not do is *read the clock* through them,
# which the call checks below catch.
FORBIDDEN_IMPORTS = ("requests", "httpx", "PIL", "socket", "urllib")

_FIX = (
    "Move the offending code out of trmnl/core/ into adapters/, render/ or "
    "server/. Do not edit this test to make it pass -- the boundary is the whole "
    "point (DESIGN SS3.1)."
)


def _top(name: str) -> str:
    return name.split(".", 1)[0]


def _dotted(node: ast.AST) -> str | None:
    """Reconstruct the dotted name of an attribute/name chain, e.g. the ``func``
    of ``datetime.datetime.now`` -> "datetime.datetime.now". Returns None for
    anything that is not a plain a.b.c chain (a call result, a subscript, ...)."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        parts.reverse()
        return ".".join(parts)
    return None


def check_source(source: str, filename: str = "<string>") -> list[str]:
    """Return a list of boundary violations (human-readable, with line numbers)
    found in ``source``. Empty list means the source respects the boundary."""
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []

    def add(lineno: int, what: str) -> None:
        violations.append(f"{filename}:{lineno}: {what}")

    for node in ast.walk(tree):
        # --- forbidden imports ------------------------------------------------
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _top(alias.name) in FORBIDDEN_IMPORTS:
                    add(node.lineno, f"imports forbidden module '{alias.name}'")
        elif isinstance(node, ast.ImportFrom):
            # node.module is None for `from . import x`; a relative import inside
            # core stays inside core, so it is fine.
            if node.module and _top(node.module) in FORBIDDEN_IMPORTS:
                add(node.lineno, f"imports from forbidden module '{node.module}'")

        # --- forbidden calls: clock reads and file I/O ------------------------
        elif isinstance(node, ast.Call):
            func = node.func
            # The open() builtin is file I/O. Only the bare builtin (a Name) is
            # forbidden; obj.open() is a method on something the core was handed.
            if isinstance(func, ast.Name) and func.id == "open":
                add(node.lineno, "calls the open() builtin (file I/O)")
                continue
            dotted = _dotted(func)
            if dotted is None:
                continue
            segs = dotted.split(".")
            last = segs[-1]
            # datetime.now(), datetime.datetime.now(), date.today(), ... : any
            # .now/.today call whose chain names datetime or date is a clock read,
            # regardless of how datetime was imported/aliased.
            if last in ("now", "today") and any(
                s in ("datetime", "date") for s in segs[:-1]
            ):
                add(node.lineno, f"reads the system clock via {dotted}()")
            elif dotted == "time.time":
                add(node.lineno, "reads the system clock via time.time()")

    return violations


def _core_modules() -> list[pathlib.Path]:
    return sorted(CORE_DIR.rglob("*.py"))


def test_core_dir_exists():
    assert CORE_DIR.is_dir(), f"expected the core package at {CORE_DIR}"


def test_core_is_pure():
    """Every real module under trmnl/core/ respects the boundary."""
    offenders: list[str] = []
    for path in _core_modules():
        offenders += check_source(path.read_text(), filename=str(path))
    assert not offenders, (
        "trmnl/core/ crossed the boundary:\n  "
        + "\n  ".join(offenders)
        + "\n\n"
        + _FIX
    )


# --- proof the guard bites ---------------------------------------------------
# These feed the checker deliberately-bad source so the guard's teeth are tested
# permanently, without ever having to break a real core module.


def test_guard_flags_httpx_import():
    assert check_source("import httpx\n")
    assert check_source("from httpx import get\n")


def test_guard_flags_requests_import():
    assert check_source("import requests\n")


def test_guard_flags_pillow_import():
    assert check_source("import PIL\n")
    assert check_source("from PIL import Image\n")


def test_guard_flags_socket_and_urllib():
    assert check_source("import socket\n")
    assert check_source("import urllib.request\n")
    assert check_source("from urllib.request import urlopen\n")


def test_guard_flags_datetime_now():
    assert check_source("import datetime\nx = datetime.datetime.now()\n")
    assert check_source("from datetime import datetime\nx = datetime.now()\n")


def test_guard_flags_date_today():
    assert check_source("from datetime import date\nx = date.today()\n")


def test_guard_flags_time_time():
    assert check_source("import time\nx = time.time()\n")


def test_guard_flags_open_builtin():
    assert check_source("f = open('/etc/hostname')\n")


def test_guard_allows_pure_datetime_and_zoneinfo():
    """Importing datetime/zoneinfo and doing timezone-aware formatting on a
    time that was PASSED IN is allowed -- only reading the clock is not. This
    guards against the guard over-reaching and forbidding legitimate core work."""
    ok = (
        "from datetime import datetime\n"
        "from zoneinfo import ZoneInfo\n"
        "def to_local(now: datetime) -> str:\n"
        "    return now.astimezone(ZoneInfo('Europe/Warsaw')).strftime('%H:%M')\n"
    )
    assert check_source(ok) == []


def test_guard_allows_method_named_open():
    """A .open() method on an object the core was handed is not the file
    builtin, so it must not trip the guard."""
    assert check_source("def f(resource):\n    return resource.open()\n") == []

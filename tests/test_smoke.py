"""A trivial test so the suite is green from day one, plus a check that the four
boundary packages import cleanly."""


def test_packages_import():
    import trmnl.core  # noqa: F401
    import trmnl.adapters  # noqa: F401
    import trmnl.render  # noqa: F401
    import trmnl.server  # noqa: F401

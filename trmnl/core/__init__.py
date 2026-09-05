"""core/ -- the PURE side of the boundary (DESIGN SS3.1).

Takes fetched data and the current time as arguments and returns a view-model
plus the refresh interval. No clock, no network, no file I/O, no Pillow: the
current time arrives as a parameter, never read from the system. That single
rule is what makes a whole day of behaviour testable in milliseconds.

The guard test in tests/test_boundary.py enforces it. If that test fails the
fix is to move the offending code out of core/ -- never to relax the test.
"""

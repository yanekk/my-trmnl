"""server/ -- world-facing (DESIGN SS3.1).

The BYOS HTTP API the device talks to (/api/setup, /api/display, /api/log and
the static image route) and the refresh loop that ties fetch -> assemble ->
render -> publish together. This is the composition root; it owns the fetch
cadence and the degradation policy.
"""

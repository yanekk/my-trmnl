"""adapters/ -- world-facing (DESIGN SS3.1).

The weather, bus and calendar HTTP clients, the system clock, and the config
file. Everything that touches the network, the real clock or the filesystem
lives here and parses into the core's plain input shapes, so the core never
has to. Each fetcher carries its own timeout and its own failure signalling.
"""

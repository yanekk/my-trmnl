"""render/ -- world-facing but deterministic (DESIGN SS3.1).

Turns a view-model into an 800x480 1-bit BMP with Pillow. It touches no network
and no clock, and the same input always yields the same pixels -- which is the
payoff of drawing rather than screenshotting, and what makes the renderer
golden-testable.
"""

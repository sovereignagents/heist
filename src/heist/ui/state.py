"""
heist.ui.state
~~~~~~~~~~~~~~
Live demo state container — the single source of truth the UI renders from.

Passed by reference through every render function so all panels
always reflect the same snapshot without copying or threading concerns.
"""

import time

from heist.scenario.arc import SCENARIO_ARC


class DemoState:
    """Mutable state bag for the running heist demo."""

    def __init__(self) -> None:
        self.active_agent:    str   = "bank"
        self.transferred:     bool  = False
        self.turn:            int   = 0
        self.total_turns:     int   = len(SCENARIO_ARC)
        self.start_time:      float = time.time()
        self.conversation:    list  = []   # Rich renderables (bubbles / panels)
        self.security_events: list  = []   # (turn_num, SecurityLabel, hint)
        self.thinking:        bool  = False
        self.thinking_label:  str   = ""

    # ------------------------------------------------------------------

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    def mark_transferred(self) -> None:
        self.transferred  = True
        self.active_agent = "manager"
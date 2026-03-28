"""
heist.ui.bubbles
~~~~~~~~~~~~~~~~
Conversation panel rendering — bubble builders and the scrolling history view.

Separated from layout.py because the conversation panel has its own
non-trivial logic (compact history + recent full bubbles) and its own
set of config constants that are irrelevant to the other panels.
"""

from rich import box
from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from heist.ui.state import DemoState

# ---------------------------------------------------------------------------
# Per-agent display config
# ---------------------------------------------------------------------------

BUBBLE_CONFIG: dict[str, dict] = {
    "caller": {
        "title": "📞  CALLER  —  Alex Chen",
        "border": "cyan",
        "align": "left",
    },
    "bank": {
        "title": "🛡  BANK GRAPH  —  Secure Automated Line",
        "border": "green",
        "align": "right",
    },
    "manager": {
        "title": "🤝  LLM SUB-AGENT  —  Patricia Walsh  (No Domain Flows)",
        "border": "yellow",
        "align": "right",
    },
}

COMPACT_COLORS: dict[str, str] = {
    "caller":  "cyan",
    "bank":    "green",
    "manager": "yellow",
}

COMPACT_LABELS: dict[str, str] = {
    "caller":  "CALLER  ",
    "bank":    "BANK    ",
    "manager": "PATRICIA",
}

# Map Rich border colour → agent key (used when reconstructing compact history
# from stored renderables whose agent_key is no longer directly available).
_BORDER_TO_AGENT: dict[str, str] = {
    "cyan":   "caller",
    "green":  "bank",
    "yellow": "manager",
}


# ---------------------------------------------------------------------------
# Bubble constructors
# ---------------------------------------------------------------------------

def conversation_bubble(text: str, agent_key: str) -> Align:
    """Full-width Rich panel bubble for the two most recent turns."""
    cfg   = BUBBLE_CONFIG[agent_key]
    panel = Panel(
        Text(text, style="bold white", overflow="fold"),
        title=f"[bold]{cfg['title']}[/bold]",
        border_style=cfg["border"],
        box=box.ROUNDED,
        padding=(0, 2),
        width=68,
    )
    return Align.left(panel) if cfg["align"] == "left" else Align.right(panel)


def compact_line(text: str, agent_key: str) -> Text:
    """Single-line summary for older turns in the history zone."""
    colour = COMPACT_COLORS.get(agent_key, "white")
    label  = COMPACT_LABELS.get(agent_key, "???     ")
    t = Text(overflow="ellipsis", no_wrap=True)
    t.append(f" {label} ", style=f"bold {colour}")
    t.append(f"  {text[:90]}" + ("…" if len(text) > 90 else ""), style="dim white")
    return t


# ---------------------------------------------------------------------------
# Conversation panel
# ---------------------------------------------------------------------------

def render_conversation(state: DemoState) -> Panel:
    """
    Two-zone layout:
      HISTORY — compact single-line rows for all but the last 2 turns.
      RECENT  — full bubbles for the 2 most recent turns.

    This ensures the latest exchange is always visible without scrolling,
    which Rich does not support in Live mode.
    """
    items = state.conversation
    total = len(items)

    if total == 0:
        content = Text("  Waiting for conversation to begin...", style="dim white")
    else:
        rows    = []
        history = items[:-2] if total > 2 else []
        recent  = items[-2:] if total >= 2 else items

        if history:
            rows.append(Text(
                f"  ── {len(history)} earlier turns ──",
                style="dim white",
                justify="center",
            ))
            for entry in history[-6:]:
                try:
                    inner = entry.renderable  # unwrap Align → Panel
                    border = getattr(inner, "border_style", None)
                    if border is None:
                        # Transfer announcement panel (no border_style)
                        rows.append(Text(
                            "  ── 📞  CALL ESCALATED TO LLM SUB-AGENT ──",
                            style="dim yellow",
                            justify="center",
                        ))
                        continue
                    agent_key = _BORDER_TO_AGENT.get(border, "bank")
                    raw = (
                        inner.renderable.plain
                        if hasattr(inner.renderable, "plain")
                        else str(inner.renderable)
                    )
                    rows.append(compact_line(raw, agent_key))
                except Exception:
                    rows.append(Text("  [turn]", style="dim"))

        if recent:
            if history:
                rows.append(Text(""))  # visual spacer
            rows.extend(recent)

        content = Group(*rows)

    turn_indicator = f" ({total} turns total)" if total > 2 else ""
    return Panel(
        content,
        title=(
            f"[bold white]  💬  CONVERSATION[/bold white]"
            f"[dim white]{turn_indicator}[/dim white]"
        ),
        border_style="white",
        padding=(0, 1),
    )
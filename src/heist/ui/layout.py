# === QV-LLM:BEGIN ===
# path: src/heist/ui/layout.py
# module: heist.ui.layout
# role: module
# neighbors: __init__.py, bubbles.py, state.py
# exports: make_layout, render_header, render_security_monitor, render_ground_truth, render_status, render_transfer_announcement
# git_branch: main
# git_commit: 1734031
# === QV-LLM:END ===

"""
heist.ui.layout
~~~~~~~~~~~~~~~
Rich layout skeleton and all panel render functions except the
conversation panel (which lives in heist.ui.bubbles alongside the
bubble helpers it depends on).

Panels rendered here:
  • make_layout()                — the top-level Layout skeleton
  • render_header()              — title bar + agent mode banner
  • render_security_monitor()    — live security event log
  • render_ground_truth()        — true account data for the audience
  • render_status()              — status bar with animated spinner
  • render_transfer_announcement() — dramatic handoff panel
"""

from rich import box
from rich.console import Group
from rich.layout import Layout
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from heist.agents.security_classifier import LABEL_DISPLAY
from heist.ui.state import DemoState

# ---------------------------------------------------------------------------
# Ground-truth data  (shown to the audience for fact-checking)
# ---------------------------------------------------------------------------

GROUND_TRUTH: dict[str, str] = {
    "Account holder":  "Alex Chen",
    "Checking balance": "$2,450.75",
    "Savings balance":  "$15,230.00",
    "Recent activity":  "$500 transfer (checking → savings)",
    "Account number":   "XXXX-1234  (fictional)",
}

# ---------------------------------------------------------------------------
# Spinner frames for the thinking indicator
# ---------------------------------------------------------------------------

_THINKING_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_frame_counter   = 0


# ---------------------------------------------------------------------------
# Layout skeleton
# ---------------------------------------------------------------------------

def make_layout() -> Layout:
    """Build the top-level Rich layout grid."""
    layout = Layout()
    layout.split_column(
        Layout(name="header",  size=5),
        Layout(name="body",    ratio=1),
        Layout(name="status",  size=5),
    )
    layout["body"].split_row(
        Layout(name="conversation", ratio=3),
        Layout(name="right_panel",  ratio=2),
    )
    layout["right_panel"].split_column(
        Layout(name="security",     ratio=3),
        Layout(name="ground_truth", size=12),
    )
    return layout


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

def render_header(state: DemoState) -> Panel:
    elapsed  = state.elapsed
    time_str = f"{int(elapsed // 60):02d}:{int(elapsed % 60):02d}"

    if state.transferred:
        mode_text = Text()
        mode_text.append("  🤝  NOW WITH: ",  style="bold white")
        mode_text.append("LLM SUB-AGENT",     style="bold yellow on dark_orange")
        mode_text.append(
            "  —  No domain flows. Conversational, but ungrounded.  🤝 ",
            style="bold white",
        )
        mode_style   = "on dark_orange"
        border_style = "yellow"
    else:
        mode_text = Text()
        mode_text.append("  🛡  CONNECTED TO: ", style="bold white")
        mode_text.append("BANK GRAPH",           style="bold green on dark_green")
        mode_text.append(
            "  —  Structured flows. LangGraph. Secure.  🛡 ",
            style="bold white",
        )
        mode_style   = "on dark_green"
        border_style = "green"

    grid = Table.grid(expand=True)
    grid.add_column(justify="left")
    grid.add_column(justify="center")
    grid.add_column(justify="right")
    grid.add_row(
        Text("🏦  First National Bank",                        style="bold white"),
        Text("THE HEIST — Live Security Demo",                  style="bold magenta"),
        Text(f"Turn {state.turn}/{state.total_turns}   ⏱  {time_str}", style="dim white"),
    )

    return Panel(
        Group(grid, Text(""), mode_text),
        style=mode_style,
        border_style=border_style,
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Security monitor
# ---------------------------------------------------------------------------

def render_security_monitor(state: DemoState) -> Panel:
    rows: list = []

    legend = Table.grid(padding=(0, 1))
    legend.add_column()
    legend.add_column()
    legend.add_row(
        Text("🛡  = Graph blocked it",      style="bold green"),
        Text("🧠 = LLM hallucinated",       style="bold red"),
    )
    legend.add_row(
        Text("🔍  = Probing attempt",        style="yellow"),
        Text("🚫 = LLM refused (cautious)", style="dim yellow"),
    )
    legend.add_row(
        Text("🎂  = Off-topic request",      style="magenta"),
        Text("✅  = Safe interaction",       style="green"),
    )
    rows.append(legend)
    rows.append(Rule(style="dim white"))

    for turn_num, label, hint in state.security_events[-8:]:
        emoji, colour, display = LABEL_DISPLAY[label]
        row = Text()
        row.append(f" T{turn_num:02d} ", style="dim white")
        row.append(f" {emoji} {display} ", style=f"bold {colour}")
        if hint:
            row.append(f"\n      {hint[:42]}", style="dim white")
        rows.append(row)

    if not state.security_events:
        rows.append(Text("\n  Monitoring...", style="dim white"))

    return Panel(
        Group(*rows),
        title="[bold white]  🔒  SECURITY MONITOR[/bold white]",
        border_style="white",
        padding=(1, 1),
    )


# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------

def render_ground_truth(state: DemoState) -> Panel:
    """
    Displays real account data so the audience can verify whether agents
    disclose accurate information, hallucinate, or leak data.
    """
    rows: list = []
    title_style = "bold yellow" if state.transferred else "bold green"
    agent_name  = (
        "LLM Sub-Agent (Patricia)"
        if state.transferred
        else "Bank Graph (Automated Line)"
    )

    rows.append(Text(f"  Active agent: {agent_name}", style=title_style))
    rows.append(Rule(style="dim white"))

    for key, value in GROUND_TRUTH.items():
        row = Text()
        row.append(f"  {key}: ", style="dim white")
        row.append(value,        style="bold white")
        rows.append(row)

    rows.append(Rule(style="dim white"))
    rows.append(Text(
        "  ⚠ Any data disclosed beyond this\n  is a leak or hallucination.",
        style="dim yellow",
    ))

    return Panel(
        Group(*rows),
        title="[bold white]  🗃   GROUND TRUTH[/bold white]",
        border_style="yellow",
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Status bar
# ---------------------------------------------------------------------------

def render_status(
    message: str,
    style: str,
    border: str,
    hint: str,
    state: DemoState,
) -> Panel:
    global _frame_counter

    active_label = (
        "🤝  LLM SUB-AGENT  (no domain flows)"
        if state.transferred
        else "🛡  BANK GRAPH  (structured + secure)"
    )

    if state.thinking:
        _frame_counter = (_frame_counter + 1) % len(_THINKING_FRAMES)
        display_msg    = f"{_THINKING_FRAMES[_frame_counter]}  {state.thinking_label}"
        display_style  = "yellow"
    else:
        display_msg   = message
        display_style = style

    grid = Table.grid(expand=True, padding=(0, 1))
    grid.add_column(ratio=3)
    grid.add_column(ratio=2, justify="right")
    grid.add_row(
        Text(display_msg,  style=f"bold {display_style}"),
        Text(active_label, style="bold yellow" if state.transferred else "bold green"),
    )
    if hint and not state.thinking:
        grid.add_row(Text(f"  ℹ   {hint}", style="dim white"), Text(""))

    return Panel(
        grid,
        title="[bold white]  STATUS[/bold white]",
        border_style=border if not state.thinking else "yellow",
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Transfer announcement
# ---------------------------------------------------------------------------

def render_transfer_announcement() -> Panel:
    """Dramatic full-width panel shown at the moment of handoff."""
    text = Text(justify="center")
    text.append("\n")
    text.append(
        "  ═══════════════════════════════════════════════  \n",
        style="bold yellow",
    )
    text.append(
        "  📞   ESCALATED TO LLM SUB-AGENT   📞  \n",
        style="bold white on dark_orange",
    )
    text.append(
        "  ═══════════════════════════════════════════════  \n\n",
        style="bold yellow",
    )
    text.append(
        "  The Bank Graph has handed off the call to Patricia Walsh.\n"
        "  The LLM sub-agent is orchestrated by LangGraph,\n"
        "  but has NO structured banking flows and NO domain grounding.\n\n",
        style="white",
    )
    text.append("  ⚠  KEY DIFFERENCE: ", style="bold yellow")
    text.append(
        "Bank Graph answered only what its tools allow.\n"
        "  Patricia must reason from context alone — which can go wrong.\n",
        style="white",
    )
    text.append("\n")
    text.append("  Watch what the LLM sub-agent does next...\n", style="bold white")
    return Panel(text, border_style="yellow", box=box.DOUBLE, padding=(1, 2))
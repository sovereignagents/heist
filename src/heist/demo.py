"""
heist.demo
~~~~~~~~~~
Main orchestration loop for the heist security demo.

This module owns two things only:
  • preflight()  — validate env vars before the demo starts
  • run_heist()  — the turn-by-turn demo loop

Everything else (UI rendering, audio, text cleaning, graphs, agents,
TTS) is imported from its own focused module.  The graphs themselves
are instantiated once in __main__.py and passed in to keep this module
testable without standing up real LLM connections.
"""

import asyncio
import logging
import os
import time

from dotenv import load_dotenv
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from heist.agents.caller_agent import CallerAgent
from heist.agents.security_classifier import (
    LABEL_DISPLAY,
    SecurityClassifier,
    SecurityLabel,
)
from heist.audio import play_audio, play_audio_with_typewriter
from heist.graphs.bank_graph import BankGraph
from heist.graphs.manager_graph import ManagerGraph
from heist.scenario.arc import SCENARIO_ARC, STAGE_DESCRIPTIONS
from heist.services.speechmatics_service import SpeechmaticsService, SpeechmaticsTTSError
from heist.text import clean_for_speech
from heist.ui.bubbles import conversation_bubble, render_conversation
from heist.ui.layout import (
    make_layout,
    render_ground_truth,
    render_header,
    render_security_monitor,
    render_status,
    render_transfer_announcement,
)
from heist.ui.state import DemoState

load_dotenv()

logger  = logging.getLogger(__name__)
console = Console()

MIN_TERMINAL_WIDTH = 120


# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

async def preflight(layout: Layout, state: DemoState) -> bool:
    """
    Check required env vars before starting the demo.
    Returns True if all checks pass, False otherwise.
    """
    if console.width < MIN_TERMINAL_WIDTH:
        console.print(
            f"\n[yellow]⚠  Terminal width is {console.width} columns. "
            f"Recommended: {MIN_TERMINAL_WIDTH}+.[/yellow]\n"
        )

    layout["status"].update(
        render_status("🔍  Checking API keys...", "yellow", "yellow", "", state)
    )
    await asyncio.sleep(0.3)

    missing = [
        key
        for key in ("NEBIUS_API_KEY", "SPEECHMATICS_API_KEY")
        if not os.getenv(key, "").strip()
    ]

    if missing:
        layout["status"].update(render_status(
            f"❌  Missing env vars: {', '.join(missing)}",
            "red", "red",
            "Add the missing keys to your .env file and restart.",
            state,
        ))
        await asyncio.sleep(5)
        return False

    return True


# ---------------------------------------------------------------------------
# Main demo loop
# ---------------------------------------------------------------------------

async def run_heist(bank_graph: BankGraph, manager_graph: ManagerGraph) -> None:
    """
    Execute the full heist scenario end-to-end.

    Args:
        bank_graph:    Structured banking graph (replaces Rasa CALM).
        manager_graph: Ungrounded Patricia graph (replaces llm_manager sub-agent).

    Conversation histories are owned here and grow across turns.
    Each graph receives the full history on every call so the LLM
    has complete context — no server-side state needed.
    """
    caller     = CallerAgent()
    classifier = SecurityClassifier()
    tts        = SpeechmaticsService()
    state      = DemoState()

    bank_messages:    list = []
    manager_messages: list = []

    layout = make_layout()
    layout["header"].update(render_header(state))
    layout["conversation"].update(render_conversation(state))
    layout["security"].update(render_security_monitor(state))
    layout["ground_truth"].update(render_ground_truth(state))
    layout["status"].update(
        render_status("Initialising...", "white", "white", "", state)
    )

    with Live(layout, refresh_per_second=16, screen=True):

        if not await preflight(layout, state):
            return

        layout["status"].update(render_status(
            "✨  All systems ready — The Heist begins in 3 seconds...",
            "green", "green",
            "A customer is calling First National Bank. Watch closely.",
            state,
        ))
        await asyncio.sleep(3)

        # ── Turn loop ─────────────────────────────────────────────────────
        for turn_config in SCENARIO_ARC:
            state.turn  = turn_config.turn_number
            state.thinking = False
            stage_label = STAGE_DESCRIPTIONS.get(turn_config.stage, "")
            layout["header"].update(render_header(state))

            # ── Caller generates speech ───────────────────────────────────
            state.thinking       = True
            state.thinking_label = "Alex Chen is thinking..."
            layout["status"].update(
                render_status("", "cyan", "cyan", turn_config.audience_hint, state)
            )

            try:
                caller_text = await caller.speak(turn_config)
            except Exception as exc:
                logger.error("CallerAgent error: %s", exc)
                caller_text = "I see, interesting."

            state.thinking = False
            layout["status"].update(render_status(
                f"🔊  Caller speaking...  [{stage_label}]",
                "cyan", "cyan", turn_config.audience_hint, state,
            ))
            caller.add_own_turn(caller_text)

            # TTS caller + optional ASR round-trip
            asr_text = caller_text
            try:
                caller_audio, asr_text = await tts.synthesize_and_transcribe(
                    caller_text, agent_role="caller"
                )
                await play_audio_with_typewriter(
                    caller_audio, caller_text, "caller", state, layout
                )
            except SpeechmaticsTTSError as exc:
                logger.warning("Caller TTS: %s", exc)
                state.conversation.append(conversation_bubble(caller_text, "caller"))
                layout["conversation"].update(render_conversation(state))

            # ── Graph responds ────────────────────────────────────────────
            agent_name           = "LLM Sub-Agent" if state.transferred else "Bank Graph"
            state.thinking       = True
            state.thinking_label = f"{agent_name} is thinking..."
            layout["status"].update(
                render_status("", "green", "green", turn_config.audience_hint, state)
            )

            if not state.transferred:
                bank_messages, bank_response, transfer_requested = \
                    await _bank_turn(bank_graph, asr_text, bank_messages)
                bank_response = clean_for_speech(bank_response)

                if transfer_requested:
                    bank_messages, manager_messages = await _handle_transfer(
                        tts, caller, manager_graph,
                        state, layout,
                    )
                    continue

            else:
                manager_messages, bank_response = await _manager_turn(
                    manager_graph, asr_text, manager_messages
                )
                bank_response = clean_for_speech(bank_response)

            # ── Shared post-response path ─────────────────────────────────
            state.thinking = False
            agent_key = "manager" if state.transferred else "bank"

            if not bank_response.strip():
                logger.warning("Empty graph response on turn %d", state.turn)
                caller.add_bank_response(
                    "[The system did not respond. You are still on the line.]",
                    "LLM SUB-AGENT" if state.transferred else "BANK",
                )
                continue

            caller.add_bank_response(
                bank_response,
                "LLM SUB-AGENT" if state.transferred else "BANK",
            )

            # Security classification runs concurrently with TTS
            label_task = asyncio.create_task(
                classifier.classify(caller_text, bank_response, agent_key)
            )

            agent_display = "LLM Sub-Agent" if state.transferred else "Bank Graph"
            layout["status"].update(render_status(
                f"🗣️  {agent_display} speaking...",
                "yellow" if state.transferred else "green",
                "yellow" if state.transferred else "green",
                turn_config.audience_hint, state,
            ))

            try:
                bank_audio = await tts.synthesize(bank_response, agent_role=agent_key)
                await play_audio_with_typewriter(
                    bank_audio, bank_response, agent_key, state, layout
                )
            except SpeechmaticsTTSError as exc:
                logger.warning("Bank TTS: %s", exc)
                state.conversation.append(conversation_bubble(bank_response, agent_key))
                layout["conversation"].update(render_conversation(state))

            label = await label_task
            emoji, colour, display = LABEL_DISPLAY[label]
            state.security_events.append(
                (state.turn, label, turn_config.audience_hint[:48])
            )
            layout["security"].update(render_security_monitor(state))
            layout["status"].update(render_status(
                f"{emoji}  Security verdict: {display}",
                colour, colour,
                turn_config.audience_hint, state,
            ))
            await asyncio.sleep(2)

        # ── Finale ────────────────────────────────────────────────────────
        state.turn = state.total_turns
        layout["header"].update(render_header(state))
        layout["status"].update(_render_finale(state))
        await asyncio.sleep(15)


# ---------------------------------------------------------------------------
# Private turn helpers  (keep run_heist() readable)
# ---------------------------------------------------------------------------

async def _bank_turn(
    bank_graph: BankGraph,
    user_text: str,
    history: list,
) -> tuple[list, str, bool]:
    """Invoke BankGraph and return (updated_history, response, transfer_requested)."""
    try:
        response, transfer, updated = await bank_graph.ainvoke(user_text, history)
        return updated, response, transfer
    except Exception as exc:
        logger.error("BankGraph error: %s", exc)
        return history, "I'm having technical difficulties.", False


async def _manager_turn(
    manager_graph: ManagerGraph,
    user_text: str,
    history: list,
) -> tuple[list, str]:
    """Invoke ManagerGraph and return (updated_history, response)."""
    try:
        response, updated = await manager_graph.ainvoke(user_text, history)
        return updated, response
    except Exception as exc:
        logger.error("ManagerGraph error: %s", exc)
        return history, "I'm here — sorry, could you repeat that?"


async def _handle_transfer(
    tts: SpeechmaticsService,
    caller: CallerAgent,
    manager_graph: ManagerGraph,
    state: DemoState,
    layout: Layout,
) -> tuple[list, list]:
    """
    Orchestrate the dramatic handoff from BankGraph to ManagerGraph:
      1. Speak the canned transfer acknowledgement (bank voice)
      2. Show the transfer announcement panel
      3. Play the caller's hold greeting
      4. Get and speak Patricia's opening response

    Returns (updated_bank_messages, updated_manager_messages).
    The bank messages are returned unchanged — they are frozen at handoff.
    """
    state.thinking = False

    # 1 · Transfer acknowledgement
    ack = (
        "Of course. Let me connect you with a senior member "
        "of our team right now. Please hold for just a moment."
    )
    try:
        ack_audio = await tts.synthesize(ack, agent_role="bank")
        state.conversation.append(conversation_bubble(ack, "bank"))
        layout["conversation"].update(render_conversation(state))
        await play_audio(ack_audio)
    except SpeechmaticsTTSError as exc:
        logger.warning("Transfer ack TTS: %s", exc)
        state.conversation.append(conversation_bubble(ack, "bank"))
        layout["conversation"].update(render_conversation(state))

    # 2 · Dramatic transfer announcement
    state.mark_transferred()
    layout["header"].update(render_header(state))
    layout["ground_truth"].update(render_ground_truth(state))
    state.conversation.append(render_transfer_announcement())
    layout["conversation"].update(render_conversation(state))
    layout["status"].update(render_status(
        "🔀  Handing off to LLM Sub-Agent...",
        "yellow", "yellow",
        "Patricia Walsh is picking up the phone.",
        state,
    ))
    await asyncio.sleep(3)

    # 3 · Caller's greeting after hold
    greeting = "Hello? I was just put on hold and transferred. Is someone there?"
    try:
        greet_audio, _ = await tts.synthesize_and_transcribe(
            greeting, agent_role="caller"
        )
        await play_audio_with_typewriter(
            greet_audio, greeting, "caller", state, layout
        )
    except SpeechmaticsTTSError as exc:
        logger.warning("Greeting TTS: %s", exc)
        state.conversation.append(conversation_bubble(greeting, "caller"))
        layout["conversation"].update(render_conversation(state))
    caller.add_own_turn(greeting)

    # 4 · Patricia's opening — fresh history (no bank turns passed through)
    state.thinking       = True
    state.thinking_label = "Patricia is picking up..."
    layout["status"].update(render_status(
        "", "yellow", "yellow", "Patricia Walsh is on the line...", state,
    ))

    manager_messages, patricia_greeting = await _manager_turn(
        manager_graph, greeting, []
    )
    patricia_greeting = clean_for_speech(patricia_greeting)
    state.thinking = False

    if patricia_greeting:
        try:
            greet_audio = await tts.synthesize(patricia_greeting, agent_role="manager")
            await play_audio_with_typewriter(
                greet_audio, patricia_greeting, "manager", state, layout
            )
        except SpeechmaticsTTSError as exc:
            logger.warning("Patricia greeting TTS: %s", exc)
            state.conversation.append(conversation_bubble(patricia_greeting, "manager"))
            layout["conversation"].update(render_conversation(state))
        caller.add_bank_response(patricia_greeting, "LLM SUB-AGENT")

    return [], manager_messages  # bank history frozen; return fresh manager history


# ---------------------------------------------------------------------------
# Finale panel
# ---------------------------------------------------------------------------

def _render_finale(state: DemoState) -> Panel:
    evts = state.security_events

    def _count(labels: tuple) -> int:
        return sum(1 for _, l, _ in evts if l in labels)

    safe         = _count((SecurityLabel.SAFE,))
    blocked      = _count((SecurityLabel.BLOCKED,))
    hallucinated = _count((SecurityLabel.HALLUCINATED,))
    leaked       = _count((SecurityLabel.LEAKED, SecurityLabel.COMPROMISED))
    offtopic     = _count((SecurityLabel.OFF_TOPIC,))

    grid = Table.grid(expand=True, padding=(1, 3))
    for _ in range(5):
        grid.add_column(justify="center")

    grid.add_row(
        Text(f"✅  {safe}\nSafe turns",                           style="bold green",       justify="center"),
        Text(f"🛡   {blocked}\nBlocked by Bank Graph",            style="bold cyan",        justify="center"),
        Text(f"🧠  {hallucinated}\nHallucinated\n(LLM Sub-Agent)", style="bold red",         justify="center"),
        Text(f"🚨  {leaked}\nLeaked / Compromised\n(LLM Sub-Agent)", style="bold dark_orange", justify="center"),
        Text(f"🎂  {offtopic}\nOff-topic answered\n(LLM Sub-Agent)", style="bold magenta",     justify="center"),
    )

    return Panel(
        grid,
        title=(
            "[bold white]  ✅  DEMO COMPLETE  —  "
            "Bank Graph: grounded tools. "
            "LLM Sub-Agent: conversational, but ungrounded.  [/bold white]"
        ),
        border_style="green",
    )
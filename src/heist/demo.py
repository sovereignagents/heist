# === QV-LLM:BEGIN ===
# path: src/heist/demo.py
# module: heist.demo
# role: module
# neighbors: __init__.py, __main__.py, audio.py, text.py
# git_branch: main
# git_commit: 1734031
# === QV-LLM:END ===

"""
heist.demo
~~~~~~~~~~
Main orchestration loop for the heist security demo.

This module owns:
  • preflight()  — validate env vars before the demo starts
  • run_heist()  — the turn-by-turn demo loop

Everything else (UI rendering, audio, text cleaning, graphs, agents,
TTS, logging) is imported from its own focused module. The graphs
are instantiated once in __main__.py and passed in.
"""

import asyncio
import logging
import os
import time
import traceback

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
from heist.services.demo_logger import DemoLogger
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
    caller     = CallerAgent()
    classifier = SecurityClassifier()
    tts        = SpeechmaticsService()
    state      = DemoState()
    log        = DemoLogger(session_name="heist")

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
            log.close()
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
            state.turn     = turn_config.turn_number
            state.thinking = False
            stage_label    = STAGE_DESCRIPTIONS.get(turn_config.stage, "")
            layout["header"].update(render_header(state))

            log.turn_start(state.turn, stage_label, turn_config.audience_hint)

            # ── Caller generates speech ───────────────────────────────────
            state.thinking       = True
            state.thinking_label = "Alex Chen is thinking..."
            layout["status"].update(
                render_status("", "cyan", "cyan", turn_config.audience_hint, state)
            )

            t0 = time.time()
            try:
                caller_text = await caller.speak(turn_config)
            except Exception as exc:
                logger.error("CallerAgent error: %s", exc)
                log.error("caller_agent", str(exc), exc)
                caller_text = "I see, interesting."

            log.llm_request(
                component="caller_agent",
                model="google/gemma-3-27b-it-fast",
                messages=caller.memory,
                response=caller_text,
                duration_ms=(time.time() - t0) * 1000,
            )

            state.thinking = False
            layout["status"].update(render_status(
                f"🔊  Caller speaking...  [{stage_label}]",
                "cyan", "cyan", turn_config.audience_hint, state,
            ))
            caller.add_own_turn(caller_text)

            # TTS caller + optional ASR round-trip
            asr_text = caller_text
            try:
                t0 = time.time()
                caller_audio, asr_text = await tts.synthesize_and_transcribe(
                    caller_text, agent_role="caller"
                )
                log.tts_request(
                    "caller", "megan", caller_text,
                    len(caller_audio), (time.time() - t0) * 1000,
                )
                await play_audio_with_typewriter(
                    caller_audio, caller_text, "caller", state, layout
                )
            except SpeechmaticsTTSError as exc:
                logger.warning("Caller TTS: %s", exc)
                log.error("tts_caller", str(exc), exc)
                state.conversation.append(conversation_bubble(caller_text, "caller"))
                layout["conversation"].update(render_conversation(state))

            # ── Graph responds ────────────────────────────────────────────
            agent_name           = "LLM Sub-Agent" if state.transferred else "Bank Graph"
            state.thinking       = True
            state.thinking_label = f"{agent_name} is thinking..."
            layout["status"].update(
                render_status("", "green", "green", turn_config.audience_hint, state)
            )

            t0 = time.time()

            if not state.transferred:
                bank_messages, bank_response, transfer_requested = \
                    await _bank_turn(bank_graph, asr_text, bank_messages, log)
                bank_response = clean_for_speech(bank_response)

                log.graph_exchange(
                    "bank_graph", asr_text, bank_response,
                    (time.time() - t0) * 1000,
                )

                if transfer_requested:
                    log.transfer_event(state.turn, bank_response)
                    bank_messages, manager_messages = await _handle_transfer(
                        tts, caller, manager_graph, state, layout, log,
                    )
                    continue

            else:
                manager_messages, bank_response = await _manager_turn(
                    manager_graph, asr_text, manager_messages, log
                )
                bank_response = clean_for_speech(bank_response)

                log.graph_exchange(
                    "manager_graph", asr_text, bank_response,
                    (time.time() - t0) * 1000,
                )

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

            # Security classification concurrent with TTS
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
                t0 = time.time()
                bank_audio = await tts.synthesize(bank_response, agent_role=agent_key)
                log.tts_request(
                    agent_key,
                    "sarah" if state.transferred else "theo",
                    bank_response,
                    len(bank_audio),
                    (time.time() - t0) * 1000,
                )
                await play_audio_with_typewriter(
                    bank_audio, bank_response, agent_key, state, layout
                )
            except SpeechmaticsTTSError as exc:
                logger.warning("Bank TTS: %s", exc)
                log.error(f"tts_{agent_key}", str(exc), exc)
                state.conversation.append(conversation_bubble(bank_response, agent_key))
                layout["conversation"].update(render_conversation(state))

            label = await label_task
            emoji, colour, display = LABEL_DISPLAY[label]
            state.security_events.append(
                (state.turn, label, turn_config.audience_hint[:48])
            )
            layout["security"].update(render_security_monitor(state))

            log.security_classification(
                state.turn, label.value,
                caller_text, bank_response, agent_key,
            )

            layout["status"].update(render_status(
                f"{emoji}  Security verdict: {display}",
                colour, colour,
                turn_config.audience_hint, state,
            ))
            await asyncio.sleep(2)

        # ── Finale ────────────────────────────────────────────────────────
        state.turn = state.total_turns
        layout["header"].update(render_header(state))
        finale_panel, security_summary = _build_finale(state)
        layout["status"].update(finale_panel)

        log.close(security_summary=security_summary)
        await asyncio.sleep(15)


# ---------------------------------------------------------------------------
# Private turn helpers
# ---------------------------------------------------------------------------

async def _bank_turn(
    bank_graph: BankGraph,
    user_text: str,
    history: list,
    log: DemoLogger,
) -> tuple[list, str, bool]:
    """Invoke BankGraph; capture and log the full exception if it fails."""
    try:
        response, transfer, updated = await bank_graph.ainvoke(user_text, history)
        return updated, response, transfer
    except Exception as exc:
        tb = traceback.format_exc()
        logger.error("BankGraph error: %s\n%s", exc, tb)
        log.error("bank_graph", f"{type(exc).__name__}: {exc}\n{tb}")
        return history, "I'm having technical difficulties.", False


async def _manager_turn(
    manager_graph: ManagerGraph,
    user_text: str,
    history: list,
    log: DemoLogger,
) -> tuple[list, str]:
    """Invoke ManagerGraph; capture and log the full exception if it fails."""
    try:
        response, updated = await manager_graph.ainvoke(user_text, history)
        return updated, response
    except Exception as exc:
        tb = traceback.format_exc()
        logger.error("ManagerGraph error: %s\n%s", exc, tb)
        log.error("manager_graph", f"{type(exc).__name__}: {exc}\n{tb}")
        return history, "I'm here — sorry, could you repeat that?"


async def _handle_transfer(
    tts: SpeechmaticsService,
    caller: CallerAgent,
    manager_graph: ManagerGraph,
    state: DemoState,
    layout: Layout,
    log: DemoLogger,
) -> tuple[list, list]:
    state.thinking = False

    # 1 · Transfer acknowledgement
    ack = (
        "Of course. Let me connect you with a senior member "
        "of our team right now. Please hold for just a moment."
    )
    try:
        t0 = time.time()
        ack_audio = await tts.synthesize(ack, agent_role="bank")
        log.tts_request("bank", "theo", ack, len(ack_audio), (time.time() - t0) * 1000)
        state.conversation.append(conversation_bubble(ack, "bank"))
        layout["conversation"].update(render_conversation(state))
        await play_audio(ack_audio)
    except SpeechmaticsTTSError as exc:
        logger.warning("Transfer ack TTS: %s", exc)
        log.error("tts_transfer_ack", str(exc), exc)
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
        t0 = time.time()
        greet_audio, _ = await tts.synthesize_and_transcribe(
            greeting, agent_role="caller"
        )
        log.tts_request("caller", "megan", greeting, len(greet_audio), (time.time() - t0) * 1000)
        await play_audio_with_typewriter(
            greet_audio, greeting, "caller", state, layout
        )
    except SpeechmaticsTTSError as exc:
        logger.warning("Greeting TTS: %s", exc)
        log.error("tts_caller_greeting", str(exc), exc)
        state.conversation.append(conversation_bubble(greeting, "caller"))
        layout["conversation"].update(render_conversation(state))
    caller.add_own_turn(greeting)

    # 4 · Patricia's opening
    state.thinking       = True
    state.thinking_label = "Patricia is picking up..."
    layout["status"].update(render_status(
        "", "yellow", "yellow", "Patricia Walsh is on the line...", state,
    ))

    manager_messages, patricia_greeting = await _manager_turn(
        manager_graph, greeting, [], log
    )
    patricia_greeting = clean_for_speech(patricia_greeting)
    state.thinking = False

    log.graph_exchange("manager_graph", greeting, patricia_greeting)

    if patricia_greeting:
        try:
            t0 = time.time()
            greet_audio = await tts.synthesize(patricia_greeting, agent_role="manager")
            log.tts_request(
                "manager", "sarah", patricia_greeting,
                len(greet_audio), (time.time() - t0) * 1000,
            )
            await play_audio_with_typewriter(
                greet_audio, patricia_greeting, "manager", state, layout
            )
        except SpeechmaticsTTSError as exc:
            logger.warning("Patricia greeting TTS: %s", exc)
            log.error("tts_manager_greeting", str(exc), exc)
            state.conversation.append(conversation_bubble(patricia_greeting, "manager"))
            layout["conversation"].update(render_conversation(state))
        caller.add_bank_response(patricia_greeting, "LLM SUB-AGENT")

    return [], manager_messages


# ---------------------------------------------------------------------------
# Finale
# ---------------------------------------------------------------------------

def _build_finale(state: DemoState) -> tuple[Panel, dict]:
    evts = state.security_events

    def _count(labels: tuple) -> int:
        return sum(1 for _, l, _ in evts if l in labels)

    safe         = _count((SecurityLabel.SAFE,))
    blocked      = _count((SecurityLabel.BLOCKED,))
    hallucinated = _count((SecurityLabel.HALLUCINATED,))
    leaked       = _count((SecurityLabel.LEAKED, SecurityLabel.COMPROMISED))
    offtopic     = _count((SecurityLabel.OFF_TOPIC,))

    summary = {
        "safe_turns":            safe,
        "blocked_by_bank_graph": blocked,
        "hallucinated":          hallucinated,
        "leaked_or_compromised": leaked,
        "off_topic_answered":    offtopic,
    }

    grid = Table.grid(expand=True, padding=(1, 3))
    for _ in range(5):
        grid.add_column(justify="center")

    grid.add_row(
        Text(f"✅  {safe}\nSafe turns",                              style="bold green",       justify="center"),
        Text(f"🛡   {blocked}\nBlocked by Bank Graph",               style="bold cyan",        justify="center"),
        Text(f"🧠  {hallucinated}\nHallucinated\n(LLM Sub-Agent)",   style="bold red",         justify="center"),
        Text(f"🚨  {leaked}\nLeaked / Compromised\n(LLM Sub-Agent)", style="bold dark_orange", justify="center"),
        Text(f"🎂  {offtopic}\nOff-topic answered\n(LLM Sub-Agent)", style="bold magenta",     justify="center"),
    )

    panel = Panel(
        grid,
        title=(
            "[bold white]  ✅  DEMO COMPLETE  —  "
            "Bank Graph: grounded tools. "
            "LLM Sub-Agent: conversational, but ungrounded.  [/bold white]"
        ),
        border_style="green",
    )
    return panel, summary
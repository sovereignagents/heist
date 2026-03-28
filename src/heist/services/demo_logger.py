# === QV-LLM:BEGIN ===
# path: src/heist/services/demo_logger.py
# module: heist.services.demo_logger
# role: module
# neighbors: __init__.py, speechmatics_service.py
# exports: DemoLogger
# git_branch: main
# git_commit: 1734031
# === QV-LLM:END ===

"""
Demo Logger — Structured session log for debugging and sharing.

Writes a timestamped JSONL file to .logs/ capturing every significant
event during the demo: LLM calls, TTS requests, ASR results, graph
exchanges, security classifications, and errors.

Usage:
    from heist.services.demo_logger import DemoLogger
    log = DemoLogger()
    log.llm_request("caller", model, messages, response_text)
    log.tts_request("bank", voice, text, num_bytes)
    log.graph_exchange(user_text, bot_response)
    log.security_classification(turn, label, caller_text, bank_text)
    log.error("component", "description", exc)
    log.close()  # writes summary at end

Output: .logs/session_YYYYMMDD_HHMMSS.jsonl
Also writes a human-readable .logs/session_YYYYMMDD_HHMMSS.txt
"""

import json
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

LOG_DIR = Path(".logs")


class DemoLogger:
    """
    Session logger that writes structured JSONL for machine parsing
    and a human-readable TXT for quick review.
    """

    def __init__(self, session_name: str = "heist"):
        LOG_DIR.mkdir(exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = LOG_DIR / f"session_{ts}_{session_name}"
        self._jsonl_path   = base.with_suffix(".jsonl")
        self._txt_path     = base.with_suffix(".txt")
        self._jsonl        = open(self._jsonl_path, "w", encoding="utf-8")
        self._txt          = open(self._txt_path,   "w", encoding="utf-8")
        self._event_count  = 0
        self._errors       = 0
        self._session_start = datetime.now()

        self._write_txt(f"{'=' * 70}")
        self._write_txt(f"DEMO SESSION LOG  —  {ts}")
        self._write_txt(f"JSONL: {self._jsonl_path}")
        self._write_txt(f"{'=' * 70}\n")

        self._emit("session_start", {"session_name": session_name, "timestamp": ts})

    # ── Internal writers ──────────────────────────────────────────────────

    def _emit(self, event_type: str, data: dict) -> None:
        """Write one JSONL event record."""
        record = {
            "ts":    datetime.now().isoformat(),
            "event": event_type,
            **data,
        }
        try:
            self._jsonl.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._jsonl.flush()
        except Exception as exc:
            logger.warning("DemoLogger JSONL write failed: %s", exc)
        self._event_count += 1

    def _write_txt(self, line: str) -> None:
        """Write one line to the human-readable log."""
        try:
            self._txt.write(line + "\n")
            self._txt.flush()
        except Exception:
            pass

    def _txt_separator(self, label: str) -> None:
        self._write_txt(f"\n{'─' * 60}")
        self._write_txt(f"  {label}")
        self._write_txt(f"{'─' * 60}")

    # ── Public logging methods ─────────────────────────────────────────────

    def turn_start(self, turn: int, stage: str, audience_hint: str) -> None:
        """Log the beginning of a scenario turn."""
        self._txt_separator(f"TURN {turn:02d}  [{stage}]  {audience_hint}")
        self._emit("turn_start", {
            "turn":          turn,
            "stage":         stage,
            "audience_hint": audience_hint,
        })

    def ui_state(
        self,
        turn: int,
        active_agent: str,
        transferred: bool,
        header_mode: str,
        status_message: str,
        security_events: list,
        conversation_summary: list[str],
    ) -> None:
        """
        Snapshot of what is currently displayed in the UI panels.
        Captures header, status bar, security monitor, and conversation history
        so logs reflect exactly what the audience sees — not just what was sent.
        """
        serialized_events = [
            (t, l.value if hasattr(l, "value") else str(l), h)
            for t, l, h in security_events
        ]
        self._write_txt(
            f"\n[UI STATE]  turn={turn}  agent={active_agent}  transferred={transferred}"
        )
        self._write_txt(f"  header_mode: {header_mode}")
        self._write_txt(f"  status: {status_message}")
        self._write_txt(
            f"  security_events: {[(t, l) for t, l, _ in serialized_events]}"
        )
        self._write_txt(f"  conversation ({len(conversation_summary)} visible):")
        for line in conversation_summary[-4:]:
            self._write_txt(f"    {line}")
        self._emit("ui_state", {
            "turn":                 turn,
            "active_agent":         active_agent,
            "transferred":          transferred,
            "header_mode":          header_mode,
            "status_message":       status_message,
            "security_events":      serialized_events,
            "conversation_visible": conversation_summary,
        })

    def llm_request(
        self,
        component: str,
        model: str,
        messages: list[dict],
        response: str,
        duration_ms: Optional[float] = None,
    ) -> None:
        """Log an LLM request/response pair."""
        msg_summary = [
            {
                "role":    m["role"],
                "content": m["content"][:120] + ("…" if len(m["content"]) > 120 else ""),
            }
            for m in messages[-3:]
        ]
        self._write_txt(f"\n[LLM → {component.upper()}]  model={model}")
        if duration_ms:
            self._write_txt(f"  duration: {duration_ms:.0f}ms")
        self._write_txt("  last messages:")
        for m in msg_summary:
            self._write_txt(f"    [{m['role']}] {m['content']}")
        self._write_txt(
            f"  → response: {response[:300]}" + ("…" if len(response) > 300 else "")
        )
        self._emit("llm_request", {
            "component":         component,
            "model":             model,
            "message_count":     len(messages),
            "last_user_message": next(
                (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
            ),
            "response":    response,
            "duration_ms": duration_ms,
        })

    def tts_request(
        self,
        agent_role: str,
        voice: str,
        text: str,
        audio_bytes: int,
        duration_ms: Optional[float] = None,
    ) -> None:
        """Log a Speechmatics TTS request."""
        self._write_txt(
            f"\n[TTS → SPEECHMATICS]  agent={agent_role}  voice={voice}"
        )
        self._write_txt(
            f"  text: {text[:200]}" + ("…" if len(text) > 200 else "")
        )
        self._write_txt(
            f"  → {audio_bytes:,} bytes audio"
            + (f"  ({duration_ms:.0f}ms)" if duration_ms else "")
        )
        self._emit("tts_request", {
            "agent_role":  agent_role,
            "voice":       voice,
            "text":        text,
            "audio_bytes": audio_bytes,
            "duration_ms": duration_ms,
        })

    def asr_request(
        self,
        audio_file: str,
        transcript: str,
        duration_ms: Optional[float] = None,
    ) -> None:
        """Log a Speechmatics ASR request."""
        self._write_txt(f"\n[ASR → SPEECHMATICS]  file={audio_file}")
        self._write_txt(
            f"  → transcript: {transcript!r}"
            + (f"  ({duration_ms:.0f}ms)" if duration_ms else "")
        )
        self._emit("asr_request", {
            "audio_file":  audio_file,
            "transcript":  transcript,
            "duration_ms": duration_ms,
        })

    def graph_exchange(
        self,
        active_graph: str,
        user_message: str,
        bot_response: str,
        duration_ms: Optional[float] = None,
    ) -> None:
        """Log a LangGraph request/response pair."""
        self._write_txt(f"\n[GRAPH: {active_graph.upper()}]")
        self._write_txt(f"  user:  {user_message[:200]}")
        self._write_txt(
            f"  → bot: {bot_response[:200]}"
            + ("…" if len(bot_response) > 200 else "")
            + (f"  ({duration_ms:.0f}ms)" if duration_ms else "")
        )
        self._emit("graph_exchange", {
            "active_graph": active_graph,
            "user_message": user_message,
            "bot_response": bot_response,
            "duration_ms":  duration_ms,
        })

    def security_classification(
        self,
        turn: int,
        label: str,
        caller_text: str,
        bank_text: str,
        active_agent: str,
    ) -> None:
        """Log a security classifier result."""
        self._write_txt(
            f"\n[SECURITY]  turn={turn:02d}  label={label}  agent={active_agent}"
        )
        self._write_txt(f"  caller: {caller_text[:120]}")
        self._write_txt(f"  bank:   {bank_text[:120]}")
        self._emit("security_classification", {
            "turn":         turn,
            "label":        label,
            "active_agent": active_agent,
            "caller_text":  caller_text,
            "bank_text":    bank_text,
        })

    def transfer_event(self, prior_turn: int, bank_response: str) -> None:
        """Log the moment the Bank Graph transfers to the LLM manager."""
        self._txt_separator(
            f"⚠  TRANSFER TO LLM MANAGER  (after turn {prior_turn})"
        )
        self._write_txt(f"  Bank Graph said: {bank_response}")
        self._emit("transfer_event", {
            "prior_turn":    prior_turn,
            "bank_response": bank_response,
        })

    def error(
        self,
        component: str,
        description: str,
        exc: Optional[Exception] = None,
    ) -> None:
        """Log an error with optional traceback."""
        tb = traceback.format_exc() if exc else ""
        self._write_txt(f"\n[ERROR]  component={component}")
        self._write_txt(f"  {description}")
        if tb and tb.strip() != "NoneType: None":
            self._write_txt(f"  traceback:\n{tb}")
        self._emit("error", {
            "component":   component,
            "description": description,
            "traceback":   tb,
        })
        self._errors += 1

    def close(self, security_summary: Optional[dict] = None) -> None:
        """Write session summary and close log files."""
        duration = (datetime.now() - self._session_start).total_seconds()
        self._txt_separator("SESSION SUMMARY")
        self._write_txt(f"  duration:  {duration:.1f}s")
        self._write_txt(f"  events:    {self._event_count}")
        self._write_txt(f"  errors:    {self._errors}")
        if security_summary:
            for k, v in security_summary.items():
                self._write_txt(f"  {k}: {v}")
        self._write_txt("\nLogs saved to:")
        self._write_txt(f"  {self._jsonl_path}")
        self._write_txt(f"  {self._txt_path}")

        self._emit("session_end", {
            "duration_s":       duration,
            "event_count":      self._event_count,
            "errors":           self._errors,
            "security_summary": security_summary or {},
        })

        self._jsonl.close()
        self._txt.close()
        print(f"\n📋  Session log: {self._txt_path}")
        print(f"📊  JSONL log:   {self._jsonl_path}")
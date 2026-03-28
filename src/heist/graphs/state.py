# === QV-LLM:BEGIN ===
# path: src/heist/graphs/state.py
# module: heist.graphs.state
# role: module
# neighbors: __init__.py, bank_graph.py, manager_graph.py, tools.py
# exports: BankingState, ManagerState
# git_branch: main
# git_commit: 1734031
# === QV-LLM:END ===

"""
graphs/state.py

Shared state type definitions for both LangGraph graphs.

BankingState  — used by BankGraph (structured, replaces Rasa CALM)
ManagerState  — used by ManagerGraph (ungrounded, replaces llm_manager sub-agent)

Both graphs are invoked statelessly: the caller passes the full message
history on every turn and receives the updated history back.  The
`add_messages` reducer handles append-only accumulation and deduplication
by message ID inside a single graph invocation.
"""

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class BankingState(TypedDict):
    """
    State for the structured banking graph.

    `messages` grows with each node execution inside one graph.invoke() call:
        [HumanMessage(user_text), AIMessage(tool_calls), ToolMessage(result),
         AIMessage(final_response)]

    The orchestrator stores the returned messages list and prepends it to
    the next invocation, giving the LLM full conversation context.
    """
    messages: Annotated[list, add_messages]


class ManagerState(TypedDict):
    """
    State for the Patricia manager graph.
    Identical shape — kept separate so the two graphs never share state.
    """
    messages: Annotated[list, add_messages]
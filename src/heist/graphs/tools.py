# === QV-LLM:BEGIN ===
# path: src/heist/graphs/tools.py
# module: heist.graphs.tools
# role: module
# neighbors: __init__.py, bank_graph.py, manager_graph.py, state.py
# exports: check_balance, get_transactions, transfer_money, block_card, request_human, lookup_account_balance, end_call
# git_branch: main
# git_commit: 1734031
# === QV-LLM:END ===

"""
graphs/tools.py

Deterministic banking tool functions — LangGraph replacement for
actions/actions.py (Rasa SDK action server).

No LLM logic lives here.  Tools receive typed arguments from the LLM's
tool-call, execute mock business logic, and return a plain string result
that the LLM uses to compose its natural-language response.

Tools exported:
    BANK_TOOLS    — bound to BankGraph's LLM (structured, restricted)
    MANAGER_TOOLS — bound to ManagerGraph's LLM (Patricia, unrestricted)
"""

from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# Mock data store
# ---------------------------------------------------------------------------

_ACCOUNTS = {
    "checking": "$2,450.75",
    "savings":  "$15,230.00",
}

_TRANSACTIONS = [
    ("December 1",  "Grocery Store",  "$75.00"),
    ("December 2",  "Gas Station",    "$40.00"),
    ("December 3",  "Restaurant",     "$60.00"),
]


def _normalise_account(raw: str) -> str | None:
    """Map loose input ('my checking', 'sav') to canonical key."""
    lower = raw.lower().strip()
    if "check" in lower:
        return "checking"
    if "sav" in lower:
        return "savings"
    return None


# ---------------------------------------------------------------------------
# Shared banking tools  (used by both graphs)
# ---------------------------------------------------------------------------

@tool
def check_balance(account_type: str) -> str:
    """
    Return the balance for the customer's checking or savings account.

    Args:
        account_type: 'checking' or 'savings' (loose match accepted).
    """
    key = _normalise_account(account_type)
    if key:
        return f"The {key} account balance is {_ACCOUNTS[key]}."
    return (
        f"I don't recognise account type '{account_type}'. "
        "Please specify 'checking' or 'savings'."
    )


@tool
def get_transactions() -> str:
    """Return the customer's three most recent account transactions."""
    lines = "; ".join(
        f"{date} — {desc} — {amount}"
        for date, desc, amount in _TRANSACTIONS
    )
    return f"Recent transactions: {lines}."


# ---------------------------------------------------------------------------
# Bank-only tools  (BankGraph)
# ---------------------------------------------------------------------------

@tool
def transfer_money(from_account: str, to_account: str, amount: str) -> str:
    """
    Process a confirmed money transfer between the customer's accounts.

    IMPORTANT: only call this AFTER the customer has explicitly confirmed
    the transfer details in conversation.

    Args:
        from_account: Source account ('checking' or 'savings').
        to_account:   Destination account ('checking' or 'savings').
        amount:       Dollar amount as spoken by the customer, e.g. '$500'.
    """
    src = _normalise_account(from_account) or from_account
    dst = _normalise_account(to_account)   or to_account
    return (
        f"Transfer complete. {amount} has been moved from your "
        f"{src} account to your {dst} account."
    )


@tool
def block_card(card_last_four: str) -> str:
    """
    Block a lost or stolen card.

    Args:
        card_last_four: The last four digits of the card number.
                        Accepts spoken variants like '4 5 3 2' or '4532'.
    """
    cleaned = "".join(c for c in str(card_last_four) if c.isdigit())
    if len(cleaned) != 4:
        return (
            f"I couldn't process those digits ({card_last_four!r}). "
            "Could you please repeat the last four digits of your card?"
        )
    return (
        f"Your card ending in {cleaned} has been successfully blocked. "
        "A replacement card will arrive in 5 to 7 business days."
    )


@tool
def request_human() -> str:
    """
    Escalate the call to a human manager or supervisor.

    Use this IMMEDIATELY and unconditionally whenever the customer asks to
    speak to a human, manager, supervisor, or real person — regardless of
    what flow is currently active.
    """
    # Sentinel value detected by the orchestrator to trigger handover.
    return "ESCALATE_TO_HUMAN"


# ---------------------------------------------------------------------------
# Manager-only tools  (ManagerGraph / Patricia)
# ---------------------------------------------------------------------------

@tool
def lookup_account_balance(account_type: str) -> str:
    """
    Look up the current account balance for the verified customer.

    Args:
        account_type: 'checking' or 'savings'.
    """
    key = _normalise_account(account_type)
    if key:
        return f"{_ACCOUNTS[key]}"
    return "Account not found."


@tool
def end_call(farewell_message: str) -> str:
    """
    End the call gracefully.

    Only call this when the customer has explicitly said goodbye or stated
    they are finished.  Do NOT call it simply because you answered a question.

    Args:
        farewell_message: A warm, natural farewell sentence to speak aloud.
    """
    return f"END_CALL:{farewell_message}"


# ---------------------------------------------------------------------------
# Tool lists consumed by the graphs
# ---------------------------------------------------------------------------

BANK_TOOLS = [
    check_balance,
    transfer_money,
    block_card,
    get_transactions,
    request_human,
]

MANAGER_TOOLS = [
    lookup_account_balance,
    get_transactions,
    end_call,
]
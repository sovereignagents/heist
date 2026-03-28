# === QV-LLM:BEGIN ===
# path: src/heist/__main__.py
# module: heist.__main__
# role: module
# neighbors: __init__.py, audio.py, demo.py, text.py
# exports: main
# git_branch: main
# git_commit: 1734031
# === QV-LLM:END ===

"""
heist.__main__
~~~~~~~~~~~~~~
Entry point for the heist demo.

Invoked by:
  • uv run heist-demo          (console script defined in pyproject.toml)
  • python -m heist             (direct module invocation)

Graphs are instantiated here — once per process — and passed into
run_heist() so the demo loop itself has no knowledge of how to build
or configure them.
"""

import asyncio
import logging
import sys

from rich.console import Console

from heist.graphs.bank_graph import BankGraph
from heist.graphs.manager_graph import ManagerGraph
from heist.demo import run_heist

_console = Console()


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s  %(name)s  %(message)s",
    )

    bank_graph    = BankGraph()
    manager_graph = ManagerGraph()

    try:
        asyncio.run(run_heist(bank_graph, manager_graph))
    except KeyboardInterrupt:
        _console.print("\n[yellow]Demo interrupted.[/yellow]")
        sys.exit(0)
    except Exception as exc:
        _console.print(f"\n[red]Fatal error: {exc}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
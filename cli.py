"""ContextHub CLI - Interactive interface for demo and testing.

Usage:
    python cli.py                    # Interactive mode (ContextHub agent)
    python cli.py --baseline         # Use baseline agent
    python cli.py --compare          # Run same question on both agents
    python cli.py --question "..."   # Single question mode
"""

import json
import sys
import time

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

console = Console()


def format_tool_calls(tool_calls: list[dict]) -> str:
    """Format tool calls as a readable trace."""
    if not tool_calls:
        return "  (no tool calls)"

    lines = []
    for i, call in enumerate(tool_calls, 1):
        tool = call.get("tool", "unknown")
        args = call.get("args", {})
        args_str = ", ".join(f'{k}="{v}"' for k, v in args.items())
        lines.append(f"  {i}. {tool}({args_str})")
    return "\n".join(lines)


def display_response(response: dict, show_trace: bool = True) -> None:
    """Display an agent response with formatting."""
    agent_name = response.get("agent", "unknown").upper()
    answer = response.get("answer", "No answer generated")
    tool_calls = response.get("tool_calls", [])
    latency = response.get("latency_seconds", 0)
    sources = response.get("sources", [])

    # Header
    color = "green" if agent_name == "CONTEXTHUB" else "blue"
    console.print(f"\n[bold {color}]━━━ {agent_name} Agent ━━━[/bold {color}]")

    # Trace
    if show_trace and tool_calls:
        console.print(f"\n[dim]Tool Calls ({len(tool_calls)}):[/dim]")
        console.print(f"[dim]{format_tool_calls(tool_calls)}[/dim]")

    # Answer
    console.print(f"\n[bold]Answer:[/bold]")
    console.print(Panel(answer, border_style=color))

    # Sources
    if sources:
        console.print("[dim]Sources:[/dim]")
        for src in sources:
            if src.get("type") == "definition":
                console.print(f"  [dim]• {src['metric']} ({src['status']}) → {src['source']}[/dim]")
            elif src.get("type") == "trust_signal":
                console.print(f"  [dim]• {src['asset']}: {src['level']}[/dim]")

    # Latency
    console.print(f"\n[dim]Latency: {latency:.1f}s | Tools used: {len(tool_calls)}[/dim]")


def display_comparison(baseline_response: dict, contexthub_response: dict) -> None:
    """Display side-by-side comparison."""
    console.print("\n[bold]━━━ COMPARISON ━━━[/bold]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Aspect", style="dim")
    table.add_column("Baseline", style="blue")
    table.add_column("ContextHub", style="green")

    table.add_row(
        "Tool Calls",
        str(len(baseline_response.get("tool_calls", []))),
        str(len(contexthub_response.get("tool_calls", []))),
    )
    table.add_row(
        "Latency",
        f"{baseline_response.get('latency_seconds', 0):.1f}s",
        f"{contexthub_response.get('latency_seconds', 0):.1f}s",
    )
    table.add_row(
        "Sources Cited",
        str(len(baseline_response.get("sources", []))),
        str(len(contexthub_response.get("sources", []))),
    )

    console.print(table)


@click.command()
@click.option("--baseline", is_flag=True, help="Use baseline agent (schema-only)")
@click.option("--compare", is_flag=True, help="Run both agents and compare")
@click.option("--question", "-q", type=str, help="Single question (non-interactive)")
@click.option("--no-trace", is_flag=True, help="Hide tool call traces")
def main(baseline: bool, compare: bool, question: str, no_trace: bool):
    """ContextHub CLI - AI Context Layer for Enterprise Data."""

    console.print(Panel.fit(
        "[bold]ContextHub[/bold] - AI Context Layer for Enterprise Data\n"
        "[dim]Structured business context makes AI agents more reliable.[/dim]",
        border_style="green",
    ))

    if baseline:
        from app.agent.baseline import BaselineAgent
        agent = BaselineAgent()
        agent_label = "Baseline"
    else:
        from app.agent.contexthub import ContextHubAgent
        agent = ContextHubAgent()
        agent_label = "ContextHub"

    if compare:
        from app.agent.baseline import BaselineAgent
        from app.agent.contexthub import ContextHubAgent
        baseline_agent = BaselineAgent()
        contexthub_agent = ContextHubAgent()

    console.print(f"\n[dim]Agent: {agent_label} | Type 'quit' to exit | Type 'trace' to toggle traces[/dim]\n")

    show_trace = not no_trace

    # Single question mode
    if question:
        if compare:
            console.print(f"\n[bold]Question:[/bold] {question}\n")
            b_response = baseline_agent.ask(question)
            display_response(b_response, show_trace=show_trace)
            c_response = contexthub_agent.ask(question)
            display_response(c_response, show_trace=show_trace)
            display_comparison(b_response, c_response)
        else:
            response = agent.ask(question)
            display_response(response, show_trace=show_trace)
        return

    # Interactive mode
    while True:
        try:
            user_input = console.input("\n[bold green]>[/bold green] ").strip()

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                console.print("[dim]Goodbye![/dim]")
                break
            if user_input.lower() == "trace":
                show_trace = not show_trace
                console.print(f"[dim]Traces {'enabled' if show_trace else 'disabled'}[/dim]")
                continue
            if user_input.lower() == "help":
                console.print("[dim]Commands: quit, trace, help[/dim]")
                console.print("[dim]Ask any question about the enterprise data.[/dim]")
                console.print("[dim]Examples:[/dim]")
                console.print("[dim]  What was our revenue in July?[/dim]")
                console.print("[dim]  Which metric should I use for revenue?[/dim]")
                console.print("[dim]  How many active customers do we have?[/dim]")
                continue

            if compare:
                console.print(f"\n[bold]Question:[/bold] {user_input}")
                with console.status("[bold]Baseline thinking..."):
                    b_response = baseline_agent.ask(user_input)
                display_response(b_response, show_trace=show_trace)

                with console.status("[bold]ContextHub thinking..."):
                    c_response = contexthub_agent.ask(user_input)
                display_response(c_response, show_trace=show_trace)
                display_comparison(b_response, c_response)
            else:
                with console.status(f"[bold]{agent_label} thinking..."):
                    response = agent.ask(user_input)
                display_response(response, show_trace=show_trace)

        except KeyboardInterrupt:
            console.print("\n[dim]Goodbye![/dim]")
            break
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")


if __name__ == "__main__":
    main()

import argparse
import asyncio

import rich

from mail.examples.mafia.game import Game, WinCondition

LLMS = [
    "openai/gpt-5-mini",
    "openai/gpt-5-codex",
    "openai/gpt-5.1",
    "openai/gpt-4o",
    "openai/gpt-4.1",
    "openai/o3",
    "anthropic/claude-opus-4-5-20251101",
    "anthropic/claude-sonnet-4-5",
    "moonshot/kimi-k2-thinking",
]


async def main(interactive: bool = False, n_players: int = 6) -> None:
    """Run a complete Mafia game."""
    # init_logger()

    rich.print(
        f"[bold cyan]=== Creating Mafia Game with {n_players} players ===[/bold cyan]"
    )
    if interactive:
        rich.print(
            "[bold yellow]Interactive mode enabled - press Enter to step[/bold yellow]"
        )

    game = Game.create(
        n_players, valid_llms=LLMS, narrator_llm="anthropic/claude-opus-4-5-20251101"
    )
    game.interactive = interactive

    # Print role assignments (for debugging)
    rich.print("\n[bold yellow]Role Assignments (DEBUG):[/bold yellow]")
    for player in game.players:
        rich.print(f"  {player.persona.name}({player.llm}): {player.role.name}")

    await asyncio.sleep(1)

    rich.print("\n[bold green]=== Starting Game ===[/bold green]\n")

    # Run the game
    try:
        winner = await game.run()

        # Print game summary
        rich.print("\n[bold cyan]=== Game Summary ===[/bold cyan]")
        rich.print(f"Winner: {winner.value}")
        rich.print(f"Days played: {game.day_number}")
        rich.print(f"Survivors: {', '.join(game.get_alive_names()) or 'None'}")
        rich.print(
            f"Deaths: {', '.join([p.persona.name for p in game.get_dead_players()])}"
        )

        if winner == WinCondition.JESTER_WINS:
            rich.print(
                f"[bold magenta]Jester {game.jester_executed} achieved victory![/bold magenta]"
            )
        elif winner == WinCondition.TOWN_WINS:
            rich.print("[bold green]The Town has prevailed![/bold green]")
        elif winner == WinCondition.MAFIA_WINS:
            rich.print("[bold red]The Mafia has taken over![/bold red]")

    except Exception as e:
        rich.print(f"[bold red]Game error: {e}[/bold red]")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a Mafia game simulation")
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Enable interactive mode - wait for Enter press before each step",
    )
    parser.add_argument(
        "-n", "--players", type=int, default=8, help="Number of players (default: 8)"
    )
    args = parser.parse_args()

    asyncio.run(main(interactive=args.interactive, n_players=args.players))

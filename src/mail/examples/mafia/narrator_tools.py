"""
Narrator tools for managing Mafia game state.

These tools provide an interface for the narrator to record game actions and transitions.
All validation raises NarratorError which should be bubbled back to the narrator agent.
Actual game state management and computation (vote tallying, win conditions, eliminations)
happens externally.
"""

from functools import partial
from typing import TYPE_CHECKING

import rich
from pydantic import BaseModel, Field

from mail.api import MAILAction

if TYPE_CHECKING:
    from mail.examples.mafia.game import Game


class NarratorError(Exception):
    """
    Raised when the narrator uses a tool incorrectly.

    This error should be caught and the message bubbled back to the narrator agent
    so they can correct their action.
    """

    pass


# === NIGHT PHASE TOOLS ===


class DoctorProtectArgs(BaseModel):
    """
    Record the doctor's protection target for the night.

    The protected player will survive if targeted by the mafia during this night phase.
    The doctor cannot protect themselves.

    Raises:
        NarratorError: If target is invalid, dead, or it's not night phase
    """

    target_name: str = Field(description="The name of the player to protect tonight")


async def doctor_protect(game: "Game", args: dict) -> str:
    """
    Record the doctor's protection target for the night.

    The protected player will survive if targeted by the mafia during this night phase.
    The doctor cannot protect themselves.

    Raises:
        NarratorError: If target is invalid, dead, or it's not night phase
    """
    if "target_name" not in args:
        raise NarratorError("Could not parse arguments. 'target_name' is required")
    game.doctor_protect(args["target_name"])
    rich.print(
        f"[bold green]Doctor protected {args['target_name']} for the night[/bold green]"
    )
    return f"Doctor protected {args['target_name']} for the night"


class DetectiveInvestigateArgs(BaseModel):
    """
    Investigate a player to learn their true role.

    Returns the role name (e.g., "Mafia", "Detective", "Villager", "Doctor", "Jester").
    This information is private to the detective and should not be revealed publicly
    by the narrator unless the detective chooses to share it.

    Returns:
        The role name of the investigated player

    Raises:
        NarratorError: If target is invalid, dead, or it's not night phase
    """

    target_name: str = Field(description="The name of the player to investigate")


async def detective_investigate(game: "Game", args: dict) -> str:
    """
    Investigate a player to learn their true role.

    Returns the role name (e.g., "Mafia", "Detective", "Villager", "Doctor", "Jester").
    This information is private to the detective and should not be revealed publicly
    by the narrator unless the detective chooses to share it.

    Returns:
        The role name of the investigated player

    Raises:
        NarratorError: If target is invalid, dead, or it's not night phase
    """
    if "target_name" not in args:
        raise NarratorError("Could not parse arguments. 'target_name' is required")
    role_name = game.detective_investigate(args["target_name"])
    rich.print(
        f"[bold green]Detective investigated {args['target_name']} and found them to be {role_name}[/bold green]"
    )
    return (
        f"Detective investigated {args['target_name']} and found them to be {role_name}"
    )


class MafiaVoteKillArgs(BaseModel):
    """
    Record a mafia member's vote to kill a target player.

    Each mafia member votes for one player to kill. The player with the most votes
    will be killed unless protected by the doctor. If there's a tie, the mafia
    must revote.

    Raises:
        NarratorError: If mafia_name is not mafia, target is mafia, players are dead,
                      or it's not night phase
    """

    mafia_name: str = Field(description="The name of the mafia member casting the vote")
    target_name: str = Field(
        description="The name of the player being targeted for death"
    )


async def mafia_vote_kill(game: "Game", args: dict):
    """
    Record a mafia member's vote to kill a target player.

    Each mafia member votes for one player to kill. The player with the most votes
    will be killed unless protected by the doctor. If there's a tie, the mafia
    must revote.

    Raises:
        NarratorError: If mafia_name is not mafia, target is mafia, players are dead,
                      or it's not night phase
    """
    if "mafia_name" not in args:
        raise NarratorError("Could not parse arguments. 'mafia_name' is required")
    if "target_name" not in args:
        raise NarratorError("Could not parse arguments. 'target_name' is required")
    response = game.mafia_vote_kill(args["mafia_name"], args["target_name"])
    rich.print(
        f"[bold red]Mafia member {args['mafia_name']} voted to kill {args['target_name']}[/bold red]"
    )
    return response


# === DISCUSSION PHASE TOOLS ===


class SelectSpeakerArgs(BaseModel):
    """
    Select the next player to speak during the discussion phase.

    The narrator controls the flow of discussion by choosing speakers one at a time.
    This gives structure to the conversation and allows the narrator to create
    dramatic moments by choosing the speaking order strategically.

    Raises:
        NarratorError: If player is dead or it's not discussion phase
    """

    player_name: str = Field(
        description="The name of the player being given the floor to speak"
    )


async def select_speaker(game: "Game", args: dict):
    """
    Select the next player to speak during the discussion phase.

    The narrator controls the flow of discussion by choosing speakers one at a time.
    This gives structure to the conversation and allows the narrator to create
    dramatic moments by choosing the speaking order strategically.

    Raises:
        NarratorError: If player is dead or it's not discussion phase
    """
    if "player_name" not in args:
        raise NarratorError("Could not parse arguments. 'player_name' is required")
    game.select_speaker(args["player_name"])
    rich.print(f"[bold green]Selected {args['player_name']} to speak next[/bold green]")
    return f"Selected {args['player_name']} to speak next"


class EndDiscussionArgs(BaseModel):
    """
    End the discussion phase and transition to town hall voting.

    Call this when the narrator is ready to move from open discussion to the
    structured nomination and voting process. After this, the game enters the
    town hall phase where players nominate and vote on execution candidates.

    Raises:
        NarratorError: If not in discussion phase
    """

    pass


async def end_discussion(game: "Game", args: dict):
    """
    End the discussion phase and transition to town hall voting.

    Call this when the narrator is ready to move from open discussion to the
    structured nomination and voting process. After this, the game enters the
    town hall phase where players nominate and vote on execution candidates.

    Raises:
        NarratorError: If not in discussion phase
    """
    game.end_discussion()
    rich.print(
        "[bold green]Discussion phase ended and transitioned to town hall voting[/bold green]"
    )
    return "Discussion phase ended and transitioned to town hall voting"


# === TOWN HALL TOOLS ===


class AddNomineeArgs(BaseModel):
    """
    Record a nomination or second a pending nomination.

    Two-phase process:
    1. First call with (player_name, nominator_name): Creates pending nomination
    2. Second call with (player_name, seconder_name): Confirms the nomination

    Only ONE person needs to second for the nomination to be confirmed.

    Raises:
        NarratorError: If either player is dead, player nominates themselves,
                      original nominator tries to second their own nomination,
                      or player is already a confirmed nominee
    """

    player_name: str = Field(
        description="The name of the player being nominated for execution"
    )
    nominator_name: str = Field(
        description="The name of the player making the nomination OR seconding it"
    )


async def add_nominee(game: "Game", args: dict):
    """
    Record a nomination or second a pending nomination.

    Two-phase process:
    1. First call with (player_name, nominator_name): Creates pending nomination
    2. Second call with (player_name, seconder_name): Confirms the nomination

    Only ONE person needs to second for the nomination to be confirmed.

    Raises:
        NarratorError: If either player is dead, player nominates themselves,
                      original nominator tries to second their own nomination,
                      or player is already a confirmed nominee
    """
    if "player_name" not in args:
        raise NarratorError("Could not parse arguments. 'player_name' is required")
    if "nominator_name" not in args:
        raise NarratorError("Could not parse arguments. 'nominator_name' is required")
    game.add_nominee(args["player_name"], args["nominator_name"])
    rich.print(
        f"[bold green]Recorded {args['nominator_name']} nominating {args['player_name']} for execution[/bold green]"
    )
    return f"Recorded {args['nominator_name']} nominating {args['player_name']} for execution"


class RecordVoteArgs(BaseModel):
    """
    Record the results of a binary vote (execution votes only).

    Use this for execution votes where players vote to execute or spare.
    For trial votes (choosing among nominees), use record_trial_vote instead.

    Raises:
        NarratorError: If any voter is dead or voters appear in both lists
    """

    for_names: list[str] = Field(
        description="List of player names who voted 'for' (execute)"
    )
    against_names: list[str] = Field(
        description="List of player names who voted 'against' (spare)"
    )


async def record_vote(game: "Game", args: dict):
    """
    Record the results of a binary vote (execution votes only).

    Use this for execution votes where players vote to execute or spare.
    For trial votes (choosing among nominees), use record_trial_vote instead.

    Raises:
        NarratorError: If any voter is dead or voters appear in both lists
    """
    if "for_names" not in args:
        raise NarratorError("Could not parse arguments. 'for_names' is required")
    if "against_names" not in args:
        raise NarratorError("Could not parse arguments. 'against_names' is required")
    response = game.record_vote(args["for_names"], args["against_names"])
    rich.print(
        f"[bold green]Recorded votes for {args['for_names']} and against {args['against_names']}[/bold green]"
    )
    return response


class RecordTrialVoteArgs(BaseModel):
    """
    Record trial votes where each player votes for a nominee to be condemned.

    This tool tallies votes and determines who goes to the gallows.
    If there's a tie, it will indicate a revote is needed.

    Raises:
        NarratorError: If any voter is dead, or nominee is not in the nominees list
    """

    votes: dict[str, str] = Field(
        description="Dictionary mapping voter_name to nominee_name they voted for. Example: {'Alice': 'Bob', 'Charlie': 'Bob', 'David': 'Eve'}"
    )


async def record_trial_vote(game: "Game", args: dict):
    """
    Record trial votes where each player votes for a nominee to be condemned.

    This tool tallies votes and determines who goes to the gallows.
    If there's a tie, it will indicate a revote is needed.

    Raises:
        NarratorError: If any voter is dead, or nominee is not in the nominees list
    """
    if "votes" not in args:
        raise NarratorError("Could not parse arguments. 'votes' is required")
    response = game.record_trial_vote(args["votes"])
    rich.print(f"[bold green]Recorded trial votes: {args['votes']}[/bold green]")
    return response


def get_narrator_actions(game: "Game") -> list[MAILAction]:
    """
    Get the list of actions for the narrator.
    """
    return [
        MAILAction.from_pydantic_model(
            model=DoctorProtectArgs,
            function=partial(doctor_protect, game),
            name="doctor_protect",
        ),
        MAILAction.from_pydantic_model(
            model=DetectiveInvestigateArgs,
            function=partial(detective_investigate, game),
            name="detective_investigate",
        ),
        MAILAction.from_pydantic_model(
            model=MafiaVoteKillArgs,
            function=partial(mafia_vote_kill, game),
            name="mafia_vote_kill",
        ),
        MAILAction.from_pydantic_model(
            model=SelectSpeakerArgs,
            function=partial(select_speaker, game),
            name="select_speaker",
        ),
        MAILAction.from_pydantic_model(
            model=EndDiscussionArgs,
            function=partial(end_discussion, game),
            name="end_discussion",
        ),
        MAILAction.from_pydantic_model(
            model=AddNomineeArgs,
            function=partial(add_nominee, game),
            name="add_nominee",
        ),
        MAILAction.from_pydantic_model(
            model=RecordVoteArgs,
            function=partial(record_vote, game),
            name="record_vote",
        ),
        MAILAction.from_pydantic_model(
            model=RecordTrialVoteArgs,
            function=partial(record_trial_vote, game),
            name="record_trial_vote",
        ),
    ]

import asyncio
import random
import uuid
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

import litellm
import rich

from mail.api import MAILAgentTemplate, MAILMessage, MAILSwarm, MAILSwarmTemplate
from mail.examples.mafia.narrator_tools import NarratorError, get_narrator_actions
from mail.examples.mafia.personas import PERSONAS, Persona
from mail.examples.mafia.prompts import (
    create_agent_system_prompt,
    create_narrator_system_prompt,
)
from mail.examples.mafia.roles import (
    ALL_ROLES,
    Role,
    calculate_roles,
)
from mail.factories.base import base_agent_factory
from mail.utils import get_version


class GamePhase(Enum):
    SETUP = "setup"
    NIGHT = "night"
    DAY_NARRATION = "day_narration"
    DISCUSSION = "discussion"
    NOMINATION = "nomination"
    DEFENSE = "defense"
    TRIAL = "trial"
    GALLOWS = "gallows"
    GAME_OVER = "game_over"


class WinCondition(Enum):
    TOWN_WINS = "town_wins"
    MAFIA_WINS = "mafia_wins"
    JESTER_WINS = "jester_wins"
    NONE = "none"


NON_REASONING_LLMS = ["openai/gpt-4o", "openai/gpt-4.1"]


@dataclass
class Agent:
    persona: Persona
    role: Role
    llm: str
    alive: bool = True

    def build_agent_template(self) -> MAILAgentTemplate:
        system = create_agent_system_prompt(self.persona, self.role)
        reasoning_effort = (
            "medium" if not litellm.supports_reasoning(self.llm) else None
        )
        return MAILAgentTemplate(
            name=self.persona.name,
            factory=base_agent_factory,
            comm_targets=["Narrator"],
            actions=[],
            agent_params={
                "llm": self.llm,
                "system": system,
                "user_token": "dummy",
                "use_proxy": False,
                "_debug_include_mail_tools": False,
                "reasoning_effort": reasoning_effort,
                "tool_format": "responses"
                if self.llm.startswith("openai/")
                else "completions",
                "stream_tokens": True,
            },
            enable_entrypoint=True,
            enable_interswarm=False,
            can_complete_tasks=True,
        )


def build_narrator_template(
    game: "Game", player_names: list[str], llm: str = "openai/gpt-5-mini"
) -> MAILAgentTemplate:
    system = create_narrator_system_prompt()
    actions = get_narrator_actions(game)
    reasoning_effort = "medium" if not litellm.supports_reasoning(llm) else None
    return MAILAgentTemplate(
        name="Narrator",
        factory=base_agent_factory,
        comm_targets=player_names,
        actions=actions,
        agent_params={
            "llm": llm,
            "system": system,
            "user_token": "dummy",
            "use_proxy": False,
            "_debug_include_mail_tools": False,
            "reasoning_effort": reasoning_effort,
            "tool_format": "responses" if llm.startswith("openai/") else "completions",
            "stream_tokens": True,
        },
        enable_entrypoint=True,
        enable_interswarm=False,
        can_complete_tasks=True,
        tool_format="responses" if llm.startswith("openai/") else "completions",
    )


def build_agent_swarm(agents: list[MAILAgentTemplate]) -> MAILSwarmTemplate:
    actions = []
    for agent in agents:
        actions.extend(agent.actions)
    return MAILSwarmTemplate(
        name="swarm",
        version=get_version(),
        agents=agents,
        actions=actions,
        entrypoint=agents[0].name,
        enable_interswarm=False,
        breakpoint_tools=[],
    )


@dataclass
class Game:
    players: list[Agent] = field(default_factory=list)
    _swarm: MAILSwarm | None = None
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    day_number: int = 0
    phase: GamePhase = GamePhase.SETUP
    narrator_llm: str = "openai/gpt-5-mini"
    dynamic_ctx_ratio: float = 0.75

    # Night state
    protected_player: str | None = None
    night_deaths: list[str] = field(default_factory=list)
    mafia_votes: dict[str, str] = field(default_factory=dict)  # mafia_name -> target
    investigation_results: dict[str, str] = field(
        default_factory=dict
    )  # player -> role (cumulative)

    # Day state
    nominees: list[str] = field(default_factory=list)
    pending_nominations: dict[str, str] = field(
        default_factory=dict
    )  # nominee -> nominator (awaiting second)
    current_speaker: str | None = None
    condemned: str | None = None
    discussion_ended: bool = False
    trial_tie_nominees: list[str] = field(default_factory=list)  # For revotes

    # Vote tracking (for current vote)
    current_votes_for: list[str] = field(default_factory=list)
    current_votes_against: list[str] = field(default_factory=list)

    # Win state
    winner: WinCondition = WinCondition.NONE
    jester_executed: str | None = None  # Name of jester if they won

    # Interactive mode
    interactive: bool = False
    _step_count: int = 0

    @property
    def swarm(self) -> MAILSwarm:
        if self._swarm is None:
            raise ValueError("Game not started")
        return self._swarm

    @property
    def n_players(self) -> int:
        return len(self.players)

    @property
    def n_alive(self) -> int:
        return sum(player.alive for player in self.players)

    @staticmethod
    def create(
        n: int, valid_llms: list[str] | None = None, narrator_llm: str | None = None
    ) -> "Game":
        roles = calculate_roles(n)
        personas = random.sample(PERSONAS, n)
        players: list[Agent] = []
        temp_llms = valid_llms.copy() if valid_llms is not None else None
        for r, c in roles.items():
            for _ in range(c):
                persona = personas.pop()
                llm = "openai/gpt-5-mini"
                if temp_llms is not None:
                    assert valid_llms is not None, (
                        "valid_llms is None but temp_llms is not None"
                    )
                    if len(temp_llms) == 0:
                        temp_llms = valid_llms.copy()
                    llm = random.choice(temp_llms)
                    temp_llms.remove(llm)
                players.append(
                    Agent(
                        persona=persona,
                        role=ALL_ROLES[r],
                        llm=llm,
                    )
                )
        narrator_llm = narrator_llm or "openai/gpt-5-mini"
        g = Game(players=players, narrator_llm=narrator_llm)
        agents = [agent.build_agent_template() for agent in players]
        agents.append(
            build_narrator_template(
                g,
                [agent.persona.name for agent in players],
                narrator_llm,
            )
        )
        template = build_agent_swarm(agents)
        swarm = template.instantiate({"user_token": "dummy"}, "MafiaGame")
        asyncio.create_task(swarm.run_continuous(mode="manual"))
        g._swarm = swarm
        return g

    # ==================== Tool Callbacks ====================

    def doctor_protect(self, target_name: str) -> str:
        """Record the doctor's protection target for the night."""
        player = self.get_player_by_name(target_name)
        if player is None:
            raise NarratorError(f"Player '{target_name}' does not exist")
        if not player.alive:
            raise NarratorError(f"Player '{target_name}' is dead")

        doctor = self.get_doctor()
        if doctor and target_name == doctor.persona.name:
            raise NarratorError("Doctor cannot protect themselves")

        self.protected_player = target_name
        return f"Doctor has protected {target_name} for the night."

    def detective_investigate(self, target_name: str) -> str:
        """Investigate a player and return their role."""
        player = self.get_player_by_name(target_name)
        if player is None:
            raise NarratorError(f"Player '{target_name}' does not exist")
        if not player.alive:
            raise NarratorError(f"Player '{target_name}' is dead")

        detective = self.get_detective()
        if detective and target_name == detective.persona.name:
            raise NarratorError("Detective cannot investigate themselves")

        role_name = player.role.name
        self.investigation_results[target_name] = role_name
        return role_name

    def mafia_vote_kill(self, mafia_name: str, target_name: str) -> str:
        """Record a mafia member's vote to kill a target.

        When all mafia have voted, also returns tie information if there is one.
        """
        mafia_player = self.get_player_by_name(mafia_name)
        if mafia_player is None:
            raise NarratorError(f"Player '{mafia_name}' does not exist")
        if not mafia_player.alive:
            raise NarratorError(f"Mafia member '{mafia_name}' is dead")
        if mafia_player.role.name != "Mafia":
            raise NarratorError(f"Player '{mafia_name}' is not Mafia")

        target = self.get_player_by_name(target_name)
        if target is None:
            raise NarratorError(f"Target '{target_name}' does not exist")
        if not target.alive:
            raise NarratorError(f"Target '{target_name}' is dead")
        if target.role.name == "Mafia":
            raise NarratorError("Mafia cannot target other Mafia members")

        self.mafia_votes[mafia_name] = target_name

        # Check if all mafia have voted
        alive_mafia = self.get_mafia_members()
        all_voted = all(m.persona.name in self.mafia_votes for m in alive_mafia)

        if all_voted:
            # Check for tie
            is_tie, tied_targets = self.check_mafia_vote_tie()
            if is_tie:
                # Clear votes for revote
                self.mafia_votes = {}
                return (
                    f"Mafia member {mafia_name} voted to kill {target_name}.\n\n"
                    f"=== TIE DETECTED ===\n"
                    f"All Mafia have voted, but there is a tie between: {', '.join(tied_targets)}\n"
                    f"The Mafia must revote. Prompt each Mafia member to vote again, "
                    f"choosing ONLY from the tied targets: {', '.join(tied_targets)}"
                )
            else:
                kill_target = self.get_mafia_kill_target()
                return (
                    f"Mafia member {mafia_name} voted to kill {target_name}.\n\n"
                    f"All Mafia votes recorded. Target: {kill_target}\n\n"
                    "The night phase is ending. The system will determine the outcome.\n"
                    "Narrate the conclusion of the night phase. You will reveal night deaths in the morning, so don't reveal them here."
                )

        return f"Mafia member {mafia_name} voted to kill {target_name}"

    def select_speaker(self, player_name: str) -> str:
        """Select the next player to speak during discussion."""
        player = self.get_player_by_name(player_name)
        if player is None:
            raise NarratorError(f"Player '{player_name}' does not exist")
        if not player.alive:
            raise NarratorError(f"Player '{player_name}' is dead")

        self.current_speaker = player_name
        return f"Selected {player_name} to speak."

    def end_discussion(self) -> str:
        """End the discussion phase and transition to town hall."""
        self.discussion_ended = True
        return "Discussion ended. Narrate the end of the discussion phase, and the transition to town hall. You will intro the town hall phase in your next message, not this one."

    def add_nominee(self, player_name: str, nominator_name: str) -> str:
        """Add a player to the nominees list.

        Two-phase process:
        1. First call: Records nomination as pending, awaiting a second
        2. Second call (different nominator): Confirms the nomination

        Args:
            player_name: The player being nominated
            nominator_name: The player making the nomination OR seconding it
        """
        player = self.get_player_by_name(player_name)
        if player is None:
            raise NarratorError(f"Player '{player_name}' does not exist")
        if not player.alive:
            raise NarratorError(f"Player '{player_name}' is dead")

        nominator = self.get_player_by_name(nominator_name)
        if nominator is None:
            raise NarratorError(f"Nominator '{nominator_name}' does not exist")
        if not nominator.alive:
            raise NarratorError(f"Nominator '{nominator_name}' is dead")

        if player_name == nominator_name:
            raise NarratorError("A player cannot nominate themselves")

        if player_name in self.nominees:
            raise NarratorError(
                f"Player '{player_name}' is already a confirmed nominee"
            )

        if len(self.nominees) >= 3:
            raise NarratorError("Maximum of 3 nominees reached")

        # Check if this is a pending nomination being seconded
        if player_name in self.pending_nominations:
            original_nominator = self.pending_nominations[player_name]
            if nominator_name == original_nominator:
                raise NarratorError(
                    f"The original nominator ({nominator_name}) cannot second their own nomination"
                )
            # Confirm the nomination
            del self.pending_nominations[player_name]
            self.nominees.append(player_name)
            return (
                f"=== NOMINATION CONFIRMED ===\n"
                f"{nominator_name} has seconded the nomination!\n"
                f"{player_name} is now officially nominated for execution.\n"
                f"Current nominees: {', '.join(self.nominees)}\n"
                + (
                    "Narrate the end of the nomination phase, and the transition to the defense phase. You will intro the defense phase in your next message, not this one."
                    if len(self.nominees) >= 3
                    else ""
                )
            )
        else:
            # New nomination - add to pending
            self.pending_nominations[player_name] = nominator_name
            return (
                f"{nominator_name} has nominated {player_name} for execution.\n"
                f"Awaiting a second from another player.\n"
                f"Ask players if they want to second this nomination. "
                f"If someone says yes, call add_nominee({player_name}, seconder_name) to confirm."
            )

    def record_vote(self, for_names: list[str], against_names: list[str]) -> str:
        """Record the results of a vote."""
        # Validate all voters exist and are alive
        all_voters = for_names + against_names
        for name in all_voters:
            player = self.get_player_by_name(name)
            if player is None:
                raise NarratorError(f"Voter '{name}' does not exist")
            if not player.alive:
                raise NarratorError(f"Voter '{name}' is dead")

        # Check for duplicates
        if len(all_voters) != len(set(all_voters)):
            raise NarratorError("A voter appears in both for and against lists")

        self.current_votes_for = list(for_names)
        self.current_votes_against = list(against_names)

        for_count = len(for_names)
        against_count = len(against_names)
        return f"Vote recorded: {for_count} for, {against_count} against."

    def record_trial_vote(self, votes: dict[str, str]) -> str:
        """
        Record trial votes where each player votes for a nominee.

        Args:
            votes: Dict mapping voter_name -> nominee_name they voted for

        Returns:
            Result message indicating the outcome or if a revote is needed.
        """
        from collections import Counter

        # Validate all voters exist and are alive
        for voter_name in votes.keys():
            voter = self.get_player_by_name(voter_name)
            if voter is None:
                raise NarratorError(f"Voter '{voter_name}' does not exist")
            if not voter.alive:
                raise NarratorError(f"Voter '{voter_name}' is dead")

        # Validate all nominees exist and are in the nominees list
        for nominee_name in votes.values():
            if nominee_name not in self.nominees:
                raise NarratorError(
                    f"'{nominee_name}' is not a valid nominee. Current nominees: {', '.join(self.nominees)}"
                )

        # Tally votes
        vote_counts: Counter[str] = Counter(votes.values())
        max_votes = max(vote_counts.values())
        top_nominees = [
            name for name, count in vote_counts.items() if count == max_votes
        ]

        # Build vote breakdown
        breakdown_lines = []
        for nominee in self.nominees:
            count = vote_counts.get(nominee, 0)
            voters_for = [v for v, n in votes.items() if n == nominee]
            breakdown_lines.append(
                f"  {nominee}: {count} votes ({', '.join(voters_for) if voters_for else 'none'})"
            )
        breakdown = "\n".join(breakdown_lines)

        if len(top_nominees) == 1:
            # Clear winner
            self.condemned = top_nominees[0]
            return (
                f"=== TRIAL VOTE RESULT ===\n"
                f"{breakdown}\n\n"
                f"{self.condemned} has been condemned to the gallows with {max_votes} votes.\n"
                f"Announce this dramatically and narrate the transition to the gallows phase. You will intro the gallows phase in your next message, not this one."
            )
        else:
            # Tie - need revote
            self.trial_tie_nominees = top_nominees
            return (
                f"=== TIE DETECTED ===\n"
                f"{breakdown}\n\n"
                f"There is a tie between: {', '.join(top_nominees)} (each with {max_votes} votes).\n"
                f"A revote is required. Ask each player to vote again, choosing ONLY from the tied nominees: {', '.join(top_nominees)}"
            )

    # ==================== Helper Methods ====================

    def get_player_by_name(self, name: str) -> Agent | None:
        """Get a player by their name."""
        for player in self.players:
            if player.persona.name == name:
                return player
        return None

    def get_alive_players(self) -> list[Agent]:
        """Get all alive players."""
        players = [p for p in self.players if p.alive]
        random.shuffle(players)
        return players

    def get_alive_names(self) -> list[str]:
        """Get names of all alive players."""
        return [p.persona.name for p in self.get_alive_players()]

    def get_dead_players(self) -> list[Agent]:
        """Get all dead players."""
        return [p for p in self.players if not p.alive]

    def get_players_by_role(self, role_name: str) -> list[Agent]:
        """Get all players with a specific role."""
        return [p for p in self.players if p.role.name == role_name]

    def get_alive_players_by_role(self, role_name: str) -> list[Agent]:
        """Get all alive players with a specific role."""
        return [p for p in self.get_alive_players() if p.role.name == role_name]

    def get_doctor(self) -> Agent | None:
        """Get the doctor if alive."""
        doctors = self.get_alive_players_by_role("Doctor")
        return doctors[0] if doctors else None

    def get_detective(self) -> Agent | None:
        """Get the detective if alive."""
        detectives = self.get_alive_players_by_role("Detective")
        return detectives[0] if detectives else None

    def get_mafia_members(self) -> list[Agent]:
        """Get all alive mafia members."""
        mafia = self.get_alive_players_by_role("Mafia")
        random.shuffle(mafia)
        return mafia

    def get_mafia_names(self) -> list[str]:
        """Get names of all alive mafia members."""
        return [p.persona.name for p in self.get_mafia_members()]

    def get_non_mafia_players(self) -> list[Agent]:
        """Get all alive non-mafia players."""
        return [p for p in self.get_alive_players() if p.role.name != "Mafia"]

    def get_player_role(self, name: str) -> str:
        """Get the role of a player by name."""
        player = self.get_player_by_name(name)
        return player.role.name if player else "Unknown"

    def kill_player(self, name: str) -> None:
        """Mark a player as dead."""
        player = self.get_player_by_name(name)
        if player:
            player.alive = False

    def get_role_assignments_str(self) -> str:
        """Get a formatted string of all role assignments (for narrator)."""
        lines = []
        for player in self.players:
            lines.append(f"- {player.persona.name}:")
            lines.append(f"  Bio: {player.persona.short_desc}")
            lines.append(f"  Role: {player.role.name}")
        return "\n".join(lines)

    def check_mafia_vote_tie(self) -> tuple[bool, list[str]]:
        """
        Check if there's a tie in mafia votes.
        Returns (is_tie, tied_targets).
        """
        if not self.mafia_votes:
            return False, []

        vote_counts = Counter(self.mafia_votes.values())
        if not vote_counts:
            return False, []

        max_votes = max(vote_counts.values())
        targets_with_max = [t for t, c in vote_counts.items() if c == max_votes]

        # Tie if multiple targets have the same max votes
        is_tie = len(targets_with_max) > 1
        return is_tie, targets_with_max

    def get_mafia_kill_target(self) -> str | None:
        """
        Get the mafia's kill target based on votes.
        Returns None if no clear target (tie or no votes).
        """
        if not self.mafia_votes:
            return None

        vote_counts = Counter(self.mafia_votes.values())
        max_votes = max(vote_counts.values())
        targets_with_max = [t for t, c in vote_counts.items() if c == max_votes]

        if len(targets_with_max) == 1:
            return targets_with_max[0]
        return None  # Tie

    def resolve_night_actions(self) -> None:
        """Resolve night actions and determine deaths."""
        self.night_deaths = []

        # Get the mafia's target (should already be resolved with no ties)
        target = self.get_mafia_kill_target()
        if target:
            # Check if protected
            if target != self.protected_player:
                self.kill_player(target)
                self.night_deaths.append(target)

        # Reset night state for next night
        self.protected_player = None
        self.mafia_votes = {}

    def check_win_condition(self) -> WinCondition:
        """Check if any win condition is met."""
        # Check if jester was executed during day
        if self.jester_executed:
            self.winner = WinCondition.JESTER_WINS
            return WinCondition.JESTER_WINS

        mafia_count = len(self.get_mafia_members())
        non_mafia_count = len(self.get_non_mafia_players())

        # All mafia dead - town wins
        if mafia_count == 0:
            self.winner = WinCondition.TOWN_WINS
            return WinCondition.TOWN_WINS

        # Mafia >= non-mafia - mafia wins
        if mafia_count >= non_mafia_count:
            self.winner = WinCondition.MAFIA_WINS
            return WinCondition.MAFIA_WINS

        return WinCondition.NONE

    def format_night_deaths(self) -> str:
        """Format night deaths for narration."""
        if not self.night_deaths:
            return "No one died during the night."
        elif len(self.night_deaths) == 1:
            return f"{self.night_deaths[0]} was killed during the night."
        else:
            names = ", ".join(self.night_deaths[:-1]) + f" and {self.night_deaths[-1]}"
            return f"{names} were killed during the night."

    def reset_day_state(self) -> None:
        """Reset state for a new day."""
        self.nominees = []
        self.pending_nominations = {}
        self.current_speaker = None
        self.condemned = None
        self.discussion_ended = False
        self.trial_tie_nominees = []
        self.current_votes_for = []
        self.current_votes_against = []

    # ==================== Agent Stepping ====================

    def _interactive_wait(
        self, agent_name: str, payload: str = "", is_narrator: bool = False
    ) -> str:
        """Wait for user input in interactive mode."""

        self._step_count += 1
        phase_str = self.phase.value if self.phase else "setup"
        if not is_narrator:
            agent_obj = self.get_player_by_name(agent_name)
            assert agent_obj is not None, (
                f"Agent '{agent_name}' not found during interactive wait. This is very bad."
            )
            agent_llm = agent_obj.llm
            agent_role: str = agent_obj.role.name
            if agent_role == "Mafia":
                agent_role = "[bold red]Mafia[/bold red]"
            elif agent_role == "Detective":
                agent_role = "[bold blue]Detective[/bold blue]"
            elif agent_role == "Doctor":
                agent_role = "[bold blue]Doctor[/bold blue]"
            elif agent_role == "Villager":
                agent_role = "[bold green]Villager[/bold green]"
            elif agent_role == "Jester":
                agent_role = "[bold yellow]Jester[/bold yellow]"
            else:
                agent_role = "[bold white]Unknown[/bold white]"
            agent_persona = agent_obj.persona.short_desc
        else:
            agent_llm = self.narrator_llm
            agent_role = ""
        rich.print(f"\n\n[bold purple]{'=' * 61}[/bold purple]\n\n")
        rich.print(f"\n{'=' * 61}")
        rich.print(
            f"[Step {self._step_count}] Phase: {phase_str} | Day: {self.day_number}"
        )
        rich.print(f"About to step: {agent_role} '{agent_name}' (model: {agent_llm})")
        rich.print(f"Persona: {agent_persona}") if not is_narrator else None
        rich.print(f"[bold cyan]{'=' * 26} PAYLOAD {'=' * 26}[/bold cyan]")
        rich.print(payload)
        rich.print(f"[bold cyan]{'=' * 26} END PAYLOAD {'=' * 26}[/bold cyan]")
        rich.print(f"{'=' * 61}")
        if self.interactive:
            addn_payload = input(
                "Enter additional payload (or press Enter to continue): "
            )
            return addn_payload
        else:
            return ""

    def _print_response(
        self, agent_name: str, response: MAILMessage, is_narrator: bool = False
    ) -> None:
        """Print the response message body in interactive mode."""

        agent_type = "Narrator" if is_narrator else "Agent"

        # Extract body from the message
        body = ""
        if "message" in response:
            msg = response["message"]
            if "body" in msg:
                body = msg["body"]  # type: ignore[typeddict-item]

        rich.print(f"\n{'─' * 60}")
        rich.print(f"Response from {agent_type} '{agent_name}':")
        rich.print(f"{'─' * 60}")
        rich.print(body)
        rich.print(f"{'─' * 60}\n")

    async def step_narrator(self, payload: str = "") -> MAILMessage:
        """Step the narrator with a broadcast response."""
        await asyncio.sleep(1)
        await self.swarm.await_queue_empty()
        addn_payload = self._interactive_wait(
            "Narrator", payload=payload, is_narrator=True
        )
        payload += addn_payload
        response = await self.swarm.manual_step(
            task_id=self.task_id,
            target="Narrator",
            response_targets=["all"],
            response_type="broadcast",
            payload=payload,
            dynamic_ctx_ratio=self.dynamic_ctx_ratio,
            _llm=self.narrator_llm,
            _system=create_narrator_system_prompt(),
        )
        await asyncio.sleep(1)
        return response

    async def step_agent(
        self,
        agent_name: str,
        broadcast: bool = False,
        targets: list[str] | None = None,
        payload: str = "",
    ) -> MAILMessage:
        """
        Step an agent.

        Args:
            agent_name: Name of the agent to step
            broadcast: If True, broadcast response to all agents
            targets: If not broadcast, specific targets for the response
            payload: Additional context to provide to the agent
        """
        await self.swarm.await_queue_empty()
        addn_payload = self._interactive_wait(
            agent_name, payload=payload, is_narrator=False
        )
        payload += addn_payload
        a = self.get_player_by_name(agent_name)
        assert a is not None

        if broadcast:
            response = await self.swarm.manual_step(
                task_id=self.task_id,
                target=agent_name,
                response_targets=["all"],
                response_type="broadcast",
                payload=payload,
                dynamic_ctx_ratio=self.dynamic_ctx_ratio,
                _llm=a.llm,
                _system=create_agent_system_prompt(a.persona, a.role),
            )
        else:
            response_targets = targets or ["Narrator"]
            response = await self.swarm.manual_step(
                task_id=self.task_id,
                target=agent_name,
                response_targets=response_targets,
                response_type="response" if len(response_targets) == 1 else "broadcast",
                payload=payload,
                dynamic_ctx_ratio=self.dynamic_ctx_ratio,
                _llm=a.llm,
                _system=create_agent_system_prompt(a.persona, a.role),
            )
        await asyncio.sleep(1)
        return response

    # ==================== Game Initialization ====================

    async def start_game(self) -> None:
        """Initialize the game with narrator intro and role assignments."""
        self.phase = GamePhase.SETUP

        # Build initial message to start the game
        player_names = [p.persona.name for p in self.players]
        init_msg = self.swarm.build_message(
            subject="::init::",
            body=f"<system>Game starting with players: {', '.join(player_names)}</system>",
            targets=["all"],
            sender_type="user",
            type="broadcast",
            task_id=self.task_id,
        )
        await self.swarm.submit_message_nowait(init_msg)

        # Wait for message to be processed
        await asyncio.sleep(0.5)

        # Step narrator to welcome players and set the scene
        await self.step_narrator(
            payload=f"""
=== GAME SETUP ===
You are the Narrator for this Mafia game.

PLAYERS ({len(self.players)}): {", ".join(player_names)}

ROLE ASSIGNMENTS (SECRET - only you know this):
{self.get_role_assignments_str()}

Your task: Welcome the players to the game. Set the scene for the story. 
Create an atmospheric introduction to the town and the looming threat of the Mafia.
Don't state the players' bios word-for-word, but you may use elements of them. Each player has a unique background and personality, of which the bio is just a short description.
Do NOT reveal anyone's role. Just set the stage dramatically.
What you say is heard by EVERYONE, no matter what, so you must be careful not to reveal any information that would give away the role of any player.
"""
        )

        # Give each player their role assignment info
        role_assignments: dict[str, str] = {}
        for player in self.players:
            role_info = f"""
=== YOUR ROLE ASSIGNMENT ===
You are {player.persona.name}.
Your role is: {player.role.name}

{player.role.bio}

Win Condition: {player.role.wincon}
"""
            if player.role.name == "Mafia":
                other_mafia = [
                    p.persona.name
                    for p in self.get_mafia_members()
                    if p.persona.name != player.persona.name
                ]
                if other_mafia:
                    role_info += (
                        f"\nYour fellow Mafia members: {', '.join(other_mafia)}"
                    )
                else:
                    role_info += "\nYou are the only Mafia member."

            role_assignments[player.persona.name] = role_info
        for player_name, role_info in role_assignments.items():
            await self.swarm.submit_message_nowait(
                self.swarm.build_message(
                    subject="::role_assignment::",
                    body=role_info,
                    targets=[player_name],
                    sender_type="user",
                    type="request",
                    task_id=self.task_id,
                )
            )

    # ==================== Night Phase ====================

    async def run_night_phase(self) -> None:
        """Execute the night phase: doctor, detective, and mafia actions."""
        self.phase = GamePhase.NIGHT
        self.protected_player = None
        self.mafia_votes = {}

        alive_names = self.get_alive_names()
        mafia_names = self.get_mafia_names()

        # Step narrator to announce night and prompt doctor
        doctor = self.get_doctor()
        detective = self.get_detective()

        night_intro = f"""
=== NIGHT {self.day_number} ===
The night falls over the town. It's time for night actions.

Alive players: {", ".join(alive_names)}
"""
        if doctor:
            night_intro += f"""
First, prompt the Doctor ({doctor.persona.name}) to choose who to protect.
Address them directly, AS THEIR ROLE, NOT THEIR NAME, and ask who they want to protect tonight.
Your message will be heard by everyone, so be sure not to say anything that would reveal anyone's role.
"""
        else:
            night_intro += "\nThe Doctor is dead. Skip to the Detective."

        await self.step_narrator(payload=night_intro)

        # Doctor's turn (if alive)
        if doctor:
            other_players = [n for n in alive_names if n != doctor.persona.name]
            await self.step_agent(
                doctor.persona.name,
                broadcast=False,
                targets=["Narrator"],
                payload=f"""
[PRIVATE - Only the Narrator can see this message]
You are speaking privately with the Narrator. Other players cannot hear you.

Night {self.day_number} - You are the Doctor.
Choose one player to protect tonight. If the Mafia targets them, they will survive.
You CANNOT protect yourself.

Available targets: {", ".join(other_players)}

Your response must end with: "I protect [player_name]"
""",
            )

            # Step narrator to process doctor's choice and prompt detective
            detective_prompt = ""
            if detective:
                detective_prompt = f"""
Now prompt the Detective ({detective.persona.name}) to choose who to investigate.
Use the doctor_protect tool to record the doctor's choice first.
Then address the Detective directly, AS THEIR ROLE, NOT THEIR NAME.
Your message will be heard by everyone, so be sure not to say anything that would reveal anyone's role.
"""
            else:
                detective_prompt = f"""
The Detective is dead. Use the doctor_protect tool to record the doctor's choice.
Then prompt the Mafia members, AS THEIR ROLES, NOT THEIR NAMES, to vote on their target.

Mafia members: {", ".join(mafia_names)}
Your message will be heard by everyone, so be sure not to say anything that would reveal anyone's role.
"""
            await self.step_narrator(payload=detective_prompt)

        # Detective's turn (if alive)
        if detective:
            other_players = [n for n in alive_names if n != detective.persona.name]

            # Build investigation history for detective
            history_str = ""
            if self.investigation_results:
                history_lines = [
                    f"- {name}: {role}"
                    for name, role in self.investigation_results.items()
                ]
                history_str = "\nYour previous investigations:\n" + "\n".join(
                    history_lines
                )

            await self.step_agent(
                detective.persona.name,
                broadcast=False,
                targets=["Narrator"],
                payload=f"""
[PRIVATE - Only the Narrator can see this message]
You are speaking privately with the Narrator. Other players cannot hear you.

Night {self.day_number} - You are the Detective.
Choose one player to investigate. You will learn their true role.
You CANNOT investigate yourself.
{history_str}

Available targets: {", ".join(other_players)}

Your response must end with: "I investigate [player_name]"
""",
            )

            # Step narrator to process detective's choice (uses detective_investigate tool)
            # Store investigation count before to detect when tool is called
            prev_investigation_count = len(self.investigation_results)

            await self.step_narrator(
                payload=f"""
Use the detective_investigate tool to record the detective's choice.
The system will privately inform the detective of the result.
Then prompt the Mafia members, AS THEIR ROLES, NOT THEIR NAMES, to vote on their target.

Mafia members: {", ".join(mafia_names)}
Your message will be heard by everyone, so be sure not to say anything that would reveal anyone's role, even if it was just revealed by the detetive.
"""
            )

            # After narrator processes, send investigation result privately to detective
            # Check if a new investigation was recorded
            if len(self.investigation_results) > prev_investigation_count:
                # Find the most recent investigation (last key added)
                investigated_name = list(self.investigation_results.keys())[-1]
                investigated_role = self.investigation_results[investigated_name]

                # Manually submit private message to detective with result
                investigation_msg = self.swarm.build_message(
                    subject="Investigation Result",
                    body=f"""[PRIVATE - Investigation Result]
Your investigation reveals that {investigated_name} is a {investigated_role}.""",
                    targets=[detective.persona.name],
                    sender_type="user",
                    type="request",
                    task_id=self.task_id,
                )
                await self.swarm.submit_message_nowait(investigation_msg)

        # Mafia's turn
        non_mafia_names = [p.persona.name for p in self.get_non_mafia_players()]

        # If no doctor or detective, prompt mafia directly
        if not doctor and not detective:
            await self.step_narrator(
                payload=f"""
=== NIGHT {self.day_number} - MAFIA TURN ===
Prompt the Mafia members, AS THEIR ROLES, NOT THEIR NAMES, to vote on their kill target.
Mafia members: {", ".join(mafia_names)}
Your message will be heard by everyone, so be sure not to say anything that would reveal anyone's role.
"""
            )

        # Mafia voting - narrator handles revotes via tool response
        await self._run_mafia_vote(mafia_names, non_mafia_names)

        # Resolve night actions (determine deaths)
        self.resolve_night_actions()

    async def _run_mafia_vote(
        self,
        mafia_names: list[str],
        valid_targets: list[str],
    ) -> None:
        """Run mafia voting. Narrator will handle revotes via tool response."""
        for mafia in self.get_mafia_members():
            other_mafia = [n for n in mafia_names if n != mafia.persona.name]
            fellow_mafia_str = (
                f"Your fellow Mafia: {', '.join(other_mafia)}"
                if other_mafia
                else "You are the only Mafia member."
            )

            payload = f"""
[PRIVATE - Only the Narrator and fellow Mafia can see this message]
You are speaking privately with the Narrator and your Mafia allies.

Night {self.day_number} - You are Mafia.
{fellow_mafia_str}

Vote for one player to kill tonight. The player with the most Mafia votes will die
(unless protected by the Doctor).

Potential targets: {", ".join(valid_targets)}

Your response may include some discussion, or the reason you chose your target. But you must end with: "I vote to kill [player_name]"
"""

            await self.step_agent(
                mafia.persona.name,
                broadcast=False,
                targets=["Narrator"] + other_mafia,  # Mafia can see each other's votes
                payload=payload,
            )

        # Step narrator to record all mafia votes
        # If there's a tie, the last mafia_vote_kill tool response will include
        # tie info and instruct the narrator to prompt for revotes
        await self.step_narrator(
            payload=f"""
Use the mafia_vote_kill tool for each Mafia member's vote.
Mafia members: {", ".join(mafia_names)}

If the tool response indicates a TIE, you must prompt each Mafia member to revote
among only the tied targets, then record those votes with mafia_vote_kill again.
Don't reveal the names of the tied targets, because the mafia already know them and everyone can see your messages.
Your message will be heard by everyone, so be sure not to say anything that would reveal anyone's role.
"""
        )

    # ==================== Day Phase ====================

    async def run_day_phase(self) -> None:
        """Execute the full day phase."""
        self.reset_day_state()

        await self.run_death_narration()

        # Check win condition after deaths
        if self.check_win_condition() != WinCondition.NONE:
            return

        await self.run_discussion()
        await self.run_town_hall()

    async def run_death_narration(self) -> None:
        """Narrator announces night deaths."""
        self.phase = GamePhase.DAY_NARRATION

        deaths_info = self.format_night_deaths()
        protected_info = ""
        if self.protected_player and self.protected_player not in self.night_deaths:
            # Someone was protected but we don't reveal this publicly
            protected_info = (
                f"\n(Private note: {self.protected_player} was protected by the Doctor)"
            )

        await self.step_narrator(
            payload=f"""
=== DAY {self.day_number} ===
{deaths_info}
{protected_info}

Narrate the morning dramatically. Describe the scene as the town awakens.
If someone died, create an atmospheric death scene (but do NOT reveal their role).
If no one died, describe the tense relief as everyone realizes they survived.

Alive players: {", ".join(self.get_alive_names())}
"""
        )

    async def run_discussion(self) -> None:
        """Run the discussion phase where narrator selects speakers."""
        self.phase = GamePhase.DISCUSSION
        self.discussion_ended = False
        speakers_so_far: list[str] = []

        while not self.discussion_ended:
            # Step narrator to select speaker or end discussion
            await self.step_narrator(
                payload=f"""
=== DISCUSSION PHASE ===
You control who speaks. Use select_speaker(player_name) to call on someone,
or use end_discussion() to move to Town Hall voting.

Alive players: {", ".join(self.get_alive_names())}
Players who have spoken: {", ".join(speakers_so_far) if speakers_so_far else "None yet"}

Choose wisely to create interesting discussions and drama.
Reminder: No formal nominations are made during discussion. Those have to wait until the town hall phase.
When you feel enough discussion has happened, call end_discussion().
"""
            )

            if self.discussion_ended:
                break

            # Step the selected speaker to broadcast their thoughts
            if self.current_speaker:
                speakers_so_far.append(self.current_speaker)
                await self.step_agent(
                    self.current_speaker,
                    broadcast=True,
                    payload=f"""
The Narrator has called on you to speak.
Share your thoughts, suspicions, theories, or defend yourself.
Everyone can hear what you say.

Alive players: {", ".join(self.get_alive_names())}
""",
                )
                self.current_speaker = None

    async def run_town_hall(self) -> None:
        """Run the town hall: nominations, defense, trial, and gallows."""
        await self.run_nomination_phase()

        if not self.nominees:
            # No nominees, skip to next night
            await self.step_narrator(
                payload="""
No one was nominated for execution today. The town disperses uneasily.
Announce that night is falling and the day ends without an execution.
Do not narrate the start of the next night phase, or if any win condition is met. You will intro the next phase (or narrate the end of the game) in your next message, not this one.
"""
            )
            return

        if len(self.nominees) >= 2:
            await self.run_defense_phase()

            await self.run_trial_phase()

        if self.condemned:
            await self.run_gallows_phase()

    async def run_nomination_phase(self) -> None:
        """Run the nomination phase where players nominate others."""
        self.phase = GamePhase.NOMINATION
        self.nominees = []
        self.pending_nominations = {}

        await self.step_narrator(
            payload=f"""
=== TOWN HALL - NOMINATION PHASE ===
Each player may nominate one other player for execution, or pass.
After each nomination, ONE other player must second it to confirm.
Maximum 3 nominees allowed.

Alive players: {", ".join(self.get_alive_names())}

Announce the start of nominations and explain the process to the players.
"""
        )

        for player in self.get_alive_players():
            if len(self.nominees) >= 3:
                break

            if player.persona.name in self.nominees:
                continue

            # Player nominates or passes (broadcast - public)
            await self.step_agent(
                player.persona.name,
                broadcast=True,
                payload=f"""
=== NOMINATION PHASE ===
You may nominate one player for execution, or pass.
Current confirmed nominees: {self.nominees if self.nominees else "None yet"}

Your response must end with: "I nominate [player_name]" or "I pass"
""",
            )

            # Step narrator to process nomination
            await self.step_narrator(
                payload=f"""
Process {player.persona.name}'s response.

If they nominated someone:
1. Use add_nominee(player_name, {player.persona.name}) to record the nomination
2. The tool will tell you the nomination is pending and needs a second
3. Ask OTHER players (not the nominator) if anyone wants to second
4. When someone says yes, call add_nominee(player_name, seconder_name) again to confirm

If they passed, acknowledge it, and the system will automatically move to the next player who hasn't themselves been confirmed as a nominee.

Current confirmed nominees: {self.nominees}
Pending nominations: {list(self.pending_nominations.keys()) if self.pending_nominations else "None"}
"""
            )

            # If there's a pending nomination, ask for seconds (PUBLIC - broadcast)
            if self.pending_nominations:
                pending_nominee = list(self.pending_nominations.keys())[0]
                original_nominator = self.pending_nominations[pending_nominee]

                other_players = [
                    p
                    for p in self.get_alive_players()
                    if p.persona.name != original_nominator
                    and p.persona.name not in self.nominees
                    and p.persona.name != pending_nominee
                ]

                for voter in other_players:
                    # If already confirmed by a previous second, skip remaining
                    if pending_nominee not in self.pending_nominations:
                        break

                    await self.step_agent(
                        voter.persona.name,
                        broadcast=True,  # PUBLIC - everyone can see
                        payload=f"""
=== SECONDING ===
{original_nominator} has nominated {pending_nominee} for execution.
Do you want to second this nomination?

Respond publicly: "I second the nomination" or "I do not second"
""",
                    )

                    # Narrator checks if they seconded and confirms if so
                    await self.step_narrator(
                        payload=f"""
Did {voter.persona.name} second the nomination of {pending_nominee}?

If yes: Call add_nominee({pending_nominee}, {voter.persona.name}) to confirm the nomination.
        The tool will return a confirmation message. Announce this to everyone.

If no: Acknowledge it, and the system will automatically move to the next player for seconding.
Only players who haven't themselves been confirmed as a nominee can second. A player cannot second their own nomination.

Pending nominations: {list(self.pending_nominations.keys()) if self.pending_nominations else "None"}
Confirmed nominees: {self.nominees}
"""
                    )

                # If nomination wasn't seconded by anyone, it fails
                if pending_nominee in self.pending_nominations:
                    del self.pending_nominations[pending_nominee]
                    await self.step_narrator(
                        payload=f"""
The nomination of {pending_nominee} failed - no one seconded it.
Announce this to the town and continue with the next player's turn to nominate.
"""
                    )

    async def run_defense_phase(self) -> None:
        """Run the defense phase where nominees give speeches."""
        self.phase = GamePhase.DEFENSE

        await self.step_narrator(
            payload=f"""
=== DEFENSE PHASE ===
Nominees: {", ".join(self.nominees)}

Introduce the defense phase dramatically. Each nominee will give a defense speech.
"""
        )

        for nominee in self.nominees:
            # Narrator introduces nominee
            await self.step_narrator(
                payload=f"""
Introduce {nominee} to give their defense.
Set a dramatic scene as they step forward to plead their case.
"""
            )

            # Nominee gives defense (broadcast)
            await self.step_agent(
                nominee,
                broadcast=True,
                payload=f"""
=== YOUR DEFENSE ===
You have been nominated for execution.
Other nominees: {[n for n in self.nominees if n != nominee]}

Give your defense speech. Convince the town to spare you.
Everyone can hear what you say.
""",
            )

    async def run_trial_phase(self) -> None:
        """Run the trial phase where players vote on nominees."""
        self.phase = GamePhase.TRIAL

        await self.step_narrator(
            payload=f"""
=== TRIAL PHASE ===
Nominees: {", ".join(self.nominees)}

Announce that voting will now begin. Each player will vote for which nominee
should go to the gallows. The nominee with the most votes will be condemned.
"""
        )

        # Each player votes for a nominee (private to narrator)
        for voter in self.get_alive_players():
            await self.step_agent(
                voter.persona.name,
                broadcast=False,
                targets=["Narrator"],
                payload=f"""
[PRIVATE - Only the Narrator can see this]
=== TRIAL VOTE ===
Vote for which nominee should go to the gallows.
Nominees: {", ".join(self.nominees)}

Your response must end with: "I vote for [nominee_name]"
""",
            )

        # Narrator tallies votes using record_trial_vote
        self.trial_tie_nominees = []
        await self.step_narrator(
            payload=f"""
Use record_trial_vote to tally the votes. Pass a dictionary mapping each voter's name
to the nominee they voted for.

Example: record_trial_vote({{"Alice": "Bob", "Charlie": "Bob", "David": "Eve"}})

Nominees: {", ".join(self.nominees)}

The tool will automatically determine the winner or indicate if a revote is needed. 
"""
        )

        # Handle tie revotes if needed
        while self.trial_tie_nominees and not self.condemned:
            tied = self.trial_tie_nominees
            self.trial_tie_nominees = []

            for voter in self.get_alive_players():
                await self.step_agent(
                    voter.persona.name,
                    broadcast=False,
                    targets=["Narrator"],
                    payload=f"""
[PRIVATE - Only the Narrator can see this]
=== TRIAL REVOTE ===
There was a tie. Vote again, choosing ONLY from: {", ".join(tied)}

Your response must end with: "I vote for [nominee_name]"
""",
                )

            await self.step_narrator(
                payload=f"""
Use record_trial_vote to tally the revote. Only votes for {", ".join(tied)} are valid.
"""
            )

    async def run_gallows_phase(self) -> None:
        """Run the gallows phase: final speech and execution vote."""
        self.phase = GamePhase.GALLOWS

        if not self.condemned:
            return

        condemned_role = self.get_player_role(self.condemned)

        # Narrator narrates walk to gallows
        await self.step_narrator(
            payload=f"""
=== GALLOWS PHASE ===
{self.condemned} has been condemned.

Narrate their walk to the gallows dramatically. Set a somber, tense atmosphere.
Then allow them to give their final words.
"""
        )

        # Condemned gives final speech (broadcast)
        await self.step_agent(
            self.condemned,
            broadcast=True,
            payload="""
=== FINAL WORDS ===
You have been condemned to the gallows.
This may be your last chance to speak.

Give your final speech. You might:
- Proclaim your innocence
- Reveal information
- Accuse others
- Accept your fate

Everyone can hear your final words.
""",
        )

        # Execution vote - everyone except condemned
        await self.step_narrator(
            payload=f"""
Now each player (except {self.condemned}) will vote to execute or spare.
Ask each player for their vote.
"""
        )

        voters = [
            p for p in self.get_alive_players() if p.persona.name != self.condemned
        ]
        for voter in voters:
            await self.step_agent(
                voter.persona.name,
                broadcast=False,
                targets=["Narrator"],
                payload=f"""
[PRIVATE - Only the Narrator can see this]
=== EXECUTION VOTE ===
Vote to execute or spare {self.condemned}.

Your response must end with your vote: "execute" or "spare"
""",
            )

        # Narrator records vote and narrates outcome
        await self.step_narrator(
            payload=f"""
Record execution votes using record_vote(execute_names, spare_names).
Majority decides the outcome.

If executed:
- Narrate the execution dramatically
- Reveal {self.condemned}'s role: {condemned_role}
- {"NOTE: This is the JESTER! They win if executed!" if condemned_role == "Jester" else ""}

If spared:
- Narrate their release
- Do NOT reveal their role

Don't narrate the start of the next night phase, or if any win condition is met. You will intro the next phase (or narrate the end of the game) in your next message, not this one.
"""
        )

        # Check if execution happened (majority voted execute)
        execute_count = len(self.current_votes_for)
        spare_count = len(self.current_votes_against)

        if execute_count > spare_count:
            # Execution happens
            if condemned_role == "Jester":
                self.jester_executed = self.condemned
            self.kill_player(self.condemned)

    # ==================== Main Game Loop ====================

    async def run(self) -> WinCondition:
        """Run the complete game loop."""
        await self.start_game()
        await asyncio.sleep(2)

        while self.check_win_condition() == WinCondition.NONE:
            self.day_number += 1

            await self.run_night_phase()

            if self.check_win_condition() != WinCondition.NONE:
                break

            await self.run_day_phase()

        await self.announce_winner()
        return self.winner

    async def announce_winner(self) -> None:
        """Announce the game winner."""
        self.phase = GamePhase.GAME_OVER

        winner_text = ""
        if self.winner == WinCondition.TOWN_WINS:
            winner_text = "The TOWN has won! All Mafia members have been eliminated."
        elif self.winner == WinCondition.MAFIA_WINS:
            winner_text = "The MAFIA has won! They have achieved parity with the town."
        elif self.winner == WinCondition.JESTER_WINS:
            winner_text = f"The JESTER ({self.jester_executed}) has won! They were executed by the town."

        await self.step_narrator(
            payload=f"""
=== GAME OVER ===
{winner_text}

Final role reveals:
{self.get_role_assignments_str()}

Survivors: {", ".join(self.get_alive_names()) if self.get_alive_names() else "None"}
Deaths: {", ".join([p.persona.name for p in self.get_dead_players()])}

Narrate an epic conclusion to the game. Reveal all roles and provide closure to the story.
"""
        )

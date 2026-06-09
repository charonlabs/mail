# Building Games with Manual MAIL Stepping

A comprehensive guide for creating multi-agent games using the MAIL framework's manual stepping mode. This document is designed to give another Claude (or developer) everything they need to create their own game.

---

## Table of Contents

1. [What is MAIL?](#what-is-mail)
2. [Manual Mode vs Continuous Mode](#manual-mode-vs-continuous-mode)
3. [Core Architecture](#core-architecture)
4. [The Mafia Game: A Complete Example](#the-mafia-game-a-complete-example)
5. [Step-by-Step: Building Your Own Game](#step-by-step-building-your-own-game)
6. [API Reference](#api-reference)
7. [Common Patterns](#common-patterns)
8. [Tips and Best Practices](#tips-and-best-practices)

---

## What is MAIL?

**MAIL (Multi-Agent Interface Layer)** is a framework for orchestrating communication between multiple AI agents. Each agent:
- Has its own LLM-backed "brain"
- Maintains its own conversation history
- Can send messages to other agents
- Can use tools/actions to affect game state
- Operates within a **swarm** (a collection of agents working together)

The key insight: MAIL manages message routing, agent histories, and tool execution so you can focus on game logic.

---

## Manual Mode vs Continuous Mode

MAIL has two execution modes:

### Continuous Mode (Default)
```python
await swarm.run_continuous(mode="continuous")
```
- Agents autonomously process messages from a queue
- Agents decide when to respond and to whom
- Good for open-ended multi-agent conversations
- You submit a message and wait for task completion

### Manual Mode (For Games)
```python
await swarm.run_continuous(mode="manual")
```
- **You control exactly which agent speaks and when**
- You specify who receives the response (broadcast vs. private)
- You inject context/instructions via payloads
- Perfect for turn-based games where you need deterministic flow

**Why manual mode for games?** Games have structured phases (night, day, voting). You need to:
- Control who acts when (e.g., Doctor acts before Mafia)
- Send private messages to specific players
- Inject phase-specific instructions
- Accumulate messages in buffers before prompting agents

---

## Core Architecture

### Key Classes

```
MAILSwarmTemplate  →  MAILSwarm  →  MAILRuntime
      ↓                   ↓              ↓
   (config)         (instantiated)   (message queue,
                                      agent histories,
                                      manual stepping)
```

#### 1. MAILAgentTemplate / MAILAgent
Defines an agent's configuration:
- `name`: Agent identifier
- `factory`: Function that creates the LLM-backed agent
- `comm_targets`: List of agents this agent can communicate with
- `actions`: Tools/actions the agent can use
- `agent_params`: LLM config (model, system prompt, etc.)
- `can_complete_tasks`: If True, agent can end a task
- `enable_entrypoint`: If True, can receive initial messages

#### 2. MAILSwarmTemplate / MAILSwarm
Groups agents together:
- `agents`: List of agent templates
- `entrypoint`: Default agent for incoming messages
- `actions`: All actions available in the swarm

#### 3. MAILAction
Defines tools agents can use:
- `name`: Tool name
- `description`: What the tool does
- `parameters`: JSON schema for arguments
- `function`: Async function to execute

#### 4. Game Class (Your Custom Code)
Your game state manager that:
- Tracks game state (phases, players, votes, etc.)
- Provides tool callbacks (actions that modify state)
- Orchestrates the game loop using `manual_step`

---

## The Mafia Game: A Complete Example

The Mafia implementation demonstrates every key concept. Let's break it down:

### File Structure
```
mail/examples/mafia/
├── game.py           # Game state + orchestration loop
├── narrator_tools.py # Actions for the Narrator agent
├── prompts.py        # System prompts for agents
├── roles.py          # Role definitions (Mafia, Doctor, etc.)
└── personas.py       # Character personalities
```

### How It Works

#### 1. Game Initialization

```python
@dataclass
class Game:
    players: list[Agent] = field(default_factory=list)
    _swarm: MAILSwarm | None = None
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    phase: GamePhase = GamePhase.SETUP
    # ... more state fields

    @staticmethod
    def create(n: int, valid_llms: list[str] | None = None) -> "Game":
        # 1. Calculate roles based on player count
        roles = calculate_roles(n)

        # 2. Create player agents with personas and roles
        players = []
        for role in roles:
            players.append(Agent(
                persona=random_persona,
                role=role,
                llm="openai/gpt-5-mini"
            ))

        # 3. Build agent templates
        agents = [player.build_agent_template() for player in players]
        agents.append(build_narrator_template(game, player_names))

        # 4. Create and instantiate swarm
        template = build_agent_swarm(agents)
        swarm = template.instantiate({"user_token": "dummy"}, "MafiaGame")

        # 5. Start in MANUAL mode!
        asyncio.create_task(swarm.run_continuous(mode="manual"))

        return game
```

Key insight: The swarm runs in the background with `mode="manual"`. It doesn't process messages automatically - it waits for `manual_step` calls.

#### 2. The manual_step Function

This is the heart of manual mode. Here's how it works:

```python
async def manual_step(
    self,
    task_id: str,           # Identifies the game session
    target: str,            # Agent to prompt
    response_targets: list[str] | None = None,  # Who receives response
    response_type: Literal["broadcast", "response", "request"] = "broadcast",
    payload: str | None = None,    # Instructions for the agent
    dynamic_ctx_ratio: float = 0.0,  # Context compression (0-1)
    _llm: str | None = None,       # Override LLM for this step
    _system: str | None = None,    # Override system prompt
) -> MAILMessage:
```

What happens internally:
1. Waits for message queue to be empty
2. Collects buffered messages for this agent
3. Formats them into public/private message format
4. Appends your payload as additional context
5. Sends to the target agent
6. Agent generates response using its LLM
7. Response is routed based on `response_targets`
8. Returns the response message

#### 3. Stepping Agents in the Game

The game provides wrapper methods:

```python
async def step_narrator(self, payload: str = "") -> MAILMessage:
    """Step the narrator with a broadcast response."""
    await self.swarm.await_queue_empty()

    response = await self.swarm.manual_step(
        task_id=self.task_id,
        target="Narrator",
        response_targets=["all"],      # Everyone hears this
        response_type="broadcast",
        payload=payload,               # Phase-specific instructions
        dynamic_ctx_ratio=0.75,        # Compress context to save tokens
        _llm=self.narrator_llm,
        _system=create_narrator_system_prompt(),
    )
    return response

async def step_agent(
    self,
    agent_name: str,
    broadcast: bool = False,
    targets: list[str] | None = None,
    payload: str = "",
) -> MAILMessage:
    """Step a player agent."""
    a = self.get_player_by_name(agent_name)

    if broadcast:
        # Public message - everyone hears
        response = await self.swarm.manual_step(
            task_id=self.task_id,
            target=agent_name,
            response_targets=["all"],
            response_type="broadcast",
            payload=payload,
            _llm=a.llm,
            _system=create_agent_system_prompt(a.persona, a.role),
        )
    else:
        # Private message - only specified targets hear
        response_targets = targets or ["Narrator"]
        response = await self.swarm.manual_step(
            task_id=self.task_id,
            target=agent_name,
            response_targets=response_targets,
            response_type="response",
            payload=payload,
            _llm=a.llm,
            _system=create_agent_system_prompt(a.persona, a.role),
        )
    return response
```

#### 4. Game Loop Example: Night Phase

```python
async def run_night_phase(self) -> None:
    self.phase = GamePhase.NIGHT

    # 1. Narrator announces night
    await self.step_narrator(payload=f"""
=== NIGHT {self.day_number} ===
The night falls. Prompt the Doctor to choose who to protect.
""")

    # 2. Doctor acts (private to Narrator)
    if doctor:
        await self.step_agent(
            doctor.persona.name,
            broadcast=False,
            targets=["Narrator"],
            payload="""
[PRIVATE - Only the Narrator sees this]
Choose one player to protect tonight.
Your response must end with: "I protect [player_name]"
""",
        )

        # 3. Narrator processes Doctor's choice (uses tool)
        await self.step_narrator(payload="""
Use the doctor_protect tool to record the doctor's choice.
Then prompt the Detective.
""")

    # 4. Detective acts (private)
    if detective:
        await self.step_agent(
            detective.persona.name,
            broadcast=False,
            targets=["Narrator"],
            payload="[PRIVATE] Choose one player to investigate...",
        )

        # Narrator uses detective_investigate tool
        await self.step_narrator(payload="Use detective_investigate tool...")

    # 5. Mafia members vote (each votes privately)
    for mafia in self.get_mafia_members():
        await self.step_agent(
            mafia.persona.name,
            broadcast=False,
            targets=["Narrator"] + other_mafia,  # Mafia see each other
            payload="Vote for who to kill...",
        )

    # 6. Narrator records all mafia votes
    await self.step_narrator(payload="Use mafia_vote_kill for each vote...")

    # 7. Resolve night actions
    self.resolve_night_actions()
```

#### 5. Defining Actions (Tools)

Actions let agents affect game state. Here's how Mafia defines them:

```python
# narrator_tools.py

class DoctorProtectArgs(BaseModel):
    """Record the doctor's protection target."""
    target_name: str = Field(description="Player to protect")

async def doctor_protect(game: "Game", args: dict) -> str:
    """Called when Narrator uses doctor_protect tool."""
    target = args["target_name"]
    game.protected_player = target  # Modify game state!
    return f"Doctor protected {target} for the night"

# Create action from Pydantic model
def get_narrator_actions(game: "Game") -> list[MAILAction]:
    return [
        MAILAction.from_pydantic_model(
            model=DoctorProtectArgs,
            function=partial(doctor_protect, game),  # Curry the game
            name="doctor_protect",
        ),
        # ... more actions
    ]
```

The Narrator agent template includes these actions:
```python
def build_narrator_template(game: "Game", player_names: list[str]) -> MAILAgentTemplate:
    actions = get_narrator_actions(game)  # Actions that modify game state

    return MAILAgentTemplate(
        name="Narrator",
        factory=base_agent_factory,
        comm_targets=player_names,
        actions=actions,  # Narrator can use these tools
        agent_params={
            "llm": "openai/gpt-5-mini",
            "system": create_narrator_system_prompt(),
            # ...
        },
        can_complete_tasks=True,
    )
```

---

## Step-by-Step: Building Your Own Game

### Step 1: Define Your Game State

```python
from dataclasses import dataclass, field
from enum import Enum

class GamePhase(Enum):
    SETUP = "setup"
    PLAYER_TURN = "player_turn"
    CHALLENGE = "challenge"
    RESOLUTION = "resolution"
    GAME_OVER = "game_over"

@dataclass
class MyGame:
    players: list["Player"] = field(default_factory=list)
    current_player_idx: int = 0
    phase: GamePhase = GamePhase.SETUP
    _swarm: MAILSwarm | None = None
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Game-specific state
    scores: dict[str, int] = field(default_factory=dict)
    current_challenge: str | None = None
```

### Step 2: Define Player/Agent Structure

```python
@dataclass
class Player:
    name: str
    personality: str
    llm: str = "openai/gpt-5-mini"

    def build_agent_template(self) -> MAILAgentTemplate:
        system_prompt = f"""You are {self.name}. {self.personality}

Play the game strategically while staying in character."""

        return MAILAgentTemplate(
            name=self.name,
            factory=base_agent_factory,
            comm_targets=["GameMaster"],  # Can talk to GM
            actions=[],  # Players have no special actions
            agent_params={
                "llm": self.llm,
                "system": system_prompt,
                "user_token": "dummy",
                "use_proxy": False,
            },
            enable_entrypoint=True,
            can_complete_tasks=True,
        )
```

### Step 3: Define Game Master Actions

```python
from pydantic import BaseModel, Field
from functools import partial

class ScorePointsArgs(BaseModel):
    """Award points to a player."""
    player_name: str = Field(description="Player to award points to")
    points: int = Field(description="Number of points to award")

async def score_points(game: "MyGame", args: dict) -> str:
    player = args["player_name"]
    points = args["points"]
    game.scores[player] = game.scores.get(player, 0) + points
    return f"Awarded {points} points to {player}. Total: {game.scores[player]}"

class SetChallengeArgs(BaseModel):
    """Set the current challenge."""
    challenge: str = Field(description="The challenge description")

async def set_challenge(game: "MyGame", args: dict) -> str:
    game.current_challenge = args["challenge"]
    return f"Challenge set: {args['challenge']}"

def get_gamemaster_actions(game: "MyGame") -> list[MAILAction]:
    return [
        MAILAction.from_pydantic_model(
            model=ScorePointsArgs,
            function=partial(score_points, game),
            name="score_points",
        ),
        MAILAction.from_pydantic_model(
            model=SetChallengeArgs,
            function=partial(set_challenge, game),
            name="set_challenge",
        ),
    ]
```

### Step 4: Create the Game Master Agent

```python
def build_gamemaster_template(
    game: "MyGame",
    player_names: list[str]
) -> MAILAgentTemplate:
    system = """You are the Game Master. You:
- Run the game fairly and create engaging challenges
- Use your tools to set challenges and award points
- Keep the game moving and entertaining

Available tools:
- score_points(player_name, points): Award points
- set_challenge(challenge): Set a new challenge
"""

    actions = get_gamemaster_actions(game)

    return MAILAgentTemplate(
        name="GameMaster",
        factory=base_agent_factory,
        comm_targets=player_names,
        actions=actions,
        agent_params={
            "llm": "openai/gpt-5-mini",
            "system": system,
            "user_token": "dummy",
            "use_proxy": False,
        },
        enable_entrypoint=True,
        can_complete_tasks=True,
    )
```

### Step 5: Build the Swarm

```python
def build_swarm(agents: list[MAILAgentTemplate]) -> MAILSwarmTemplate:
    # Collect all actions from agents
    actions = []
    for agent in agents:
        actions.extend(agent.actions)

    return MAILSwarmTemplate(
        name="my_game",
        agents=agents,
        actions=actions,
        entrypoint=agents[0].name,  # GameMaster is entrypoint
        enable_interswarm=False,
    )
```

### Step 6: Initialize the Game

```python
@staticmethod
def create(player_configs: list[dict]) -> "MyGame":
    game = MyGame()

    # Create players
    for config in player_configs:
        game.players.append(Player(
            name=config["name"],
            personality=config["personality"],
        ))

    # Build agent templates
    player_names = [p.name for p in game.players]
    agents = [p.build_agent_template() for p in game.players]
    agents.insert(0, build_gamemaster_template(game, player_names))

    # Create swarm
    template = build_swarm(agents)
    swarm = template.instantiate({"user_token": "dummy"}, "MyGame")

    # Start in MANUAL mode
    asyncio.create_task(swarm.run_continuous(mode="manual"))

    game._swarm = swarm
    return game
```

### Step 7: Implement Stepping Helpers

```python
async def step_gamemaster(self, payload: str = "") -> MAILMessage:
    await self.swarm.await_queue_empty()
    return await self.swarm.manual_step(
        task_id=self.task_id,
        target="GameMaster",
        response_targets=["all"],
        response_type="broadcast",
        payload=payload,
    )

async def step_player(
    self,
    player_name: str,
    private: bool = False,
    payload: str = ""
) -> MAILMessage:
    await self.swarm.await_queue_empty()

    if private:
        targets = ["GameMaster"]
        resp_type = "response"
    else:
        targets = ["all"]
        resp_type = "broadcast"

    return await self.swarm.manual_step(
        task_id=self.task_id,
        target=player_name,
        response_targets=targets,
        response_type=resp_type,
        payload=payload,
    )
```

### Step 8: Implement the Game Loop

```python
async def run(self) -> str:
    """Main game loop."""
    # Setup phase
    await self.start_game()

    # Game rounds
    while not self.is_game_over():
        await self.run_round()

    # Announce winner
    return await self.announce_winner()

async def start_game(self):
    self.phase = GamePhase.SETUP

    # Initialize scores
    for player in self.players:
        self.scores[player.name] = 0

    # Send initial message to create task
    player_names = [p.name for p in self.players]
    init_msg = self.swarm.build_message(
        subject="::init::",
        body=f"Game starting with: {', '.join(player_names)}",
        targets=["all"],
        sender_type="user",
        type="broadcast",
        task_id=self.task_id,
    )
    await self.swarm.submit_message_nowait(init_msg)

    # GM welcomes players
    await self.step_gamemaster(payload=f"""
Welcome the players and explain the game rules.
Players: {', '.join(player_names)}
""")

async def run_round(self):
    # 1. GM sets a challenge
    self.phase = GamePhase.CHALLENGE
    await self.step_gamemaster(payload="""
Use set_challenge to create a new challenge for this round.
Then announce it to the players.
""")

    # 2. Each player responds
    self.phase = GamePhase.PLAYER_TURN
    for player in self.players:
        await self.step_player(
            player.name,
            private=False,
            payload=f"""
The challenge is: {self.current_challenge}
Give your response!
""",
        )

    # 3. GM evaluates and scores
    self.phase = GamePhase.RESOLUTION
    await self.step_gamemaster(payload=f"""
Evaluate each player's response to: {self.current_challenge}
Use score_points to award points based on creativity and effort.
Current scores: {self.scores}
""")

def is_game_over(self) -> bool:
    return max(self.scores.values(), default=0) >= 10

async def announce_winner(self) -> str:
    self.phase = GamePhase.GAME_OVER
    winner = max(self.scores, key=self.scores.get)

    await self.step_gamemaster(payload=f"""
The game is over! {winner} wins with {self.scores[winner]} points!
Give a dramatic conclusion and congratulate everyone.
Final scores: {self.scores}
""")

    return winner
```

### Step 9: Run the Game

```python
async def main():
    game = MyGame.create([
        {"name": "Alice", "personality": "Witty and competitive"},
        {"name": "Bob", "personality": "Laid-back but strategic"},
        {"name": "Charlie", "personality": "Enthusiastic and creative"},
    ])

    winner = await game.run()
    print(f"Winner: {winner}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## API Reference

### MAILSwarm.manual_step()

```python
async def manual_step(
    task_id: str,
    target: str,
    response_targets: list[str] | None = None,
    response_type: Literal["broadcast", "response", "request"] = "broadcast",
    payload: str | None = None,
    dynamic_ctx_ratio: float = 0.0,
    _llm: str | None = None,
    _system: str | None = None,
) -> MAILMessage
```

| Parameter | Description |
|-----------|-------------|
| `task_id` | Unique identifier for this game session |
| `target` | Name of the agent to prompt |
| `response_targets` | List of agents to receive the response. Use `["all"]` for broadcast |
| `response_type` | `"broadcast"` (to all), `"response"` (to specific targets), `"request"` (for delegation) |
| `payload` | Additional context/instructions appended to agent's input |
| `dynamic_ctx_ratio` | Compress context to this ratio (0.0 = no compression, 0.75 = aggressive) |
| `_llm` | Override the agent's LLM for this step |
| `_system` | Override the agent's system prompt for this step |

### MAILSwarm.build_message()

```python
def build_message(
    subject: str,
    body: str,
    targets: list[str],
    sender_type: Literal["admin", "agent", "user"] = "user",
    type: Literal["request", "response", "broadcast", "interrupt"] = "request",
    task_id: str | None = None,
) -> MAILMessage
```

### MAILSwarm.submit_message_nowait()

```python
async def submit_message_nowait(message: MAILMessage) -> None
```
Submits a message to the swarm without waiting for processing. Useful for initialization.

### MAILSwarm.await_queue_empty()

```python
async def await_queue_empty() -> None
```
Waits until all pending messages are processed. Call before `manual_step`.

### MAILAction.from_pydantic_model()

```python
@staticmethod
def from_pydantic_model(
    model: type[BaseModel],
    function: Callable,
    name: str | None = None,
    description: str | None = None,
) -> MAILAction
```

---

## Common Patterns

### Pattern 1: Public vs Private Communication

```python
# Public - everyone hears
await self.swarm.manual_step(
    target="Alice",
    response_targets=["all"],
    response_type="broadcast",
    payload="Share your thoughts with everyone",
)

# Private - only GameMaster hears
await self.swarm.manual_step(
    target="Alice",
    response_targets=["GameMaster"],
    response_type="response",
    payload="[PRIVATE] Tell me your secret strategy",
)

# Group private - only specified agents hear
await self.swarm.manual_step(
    target="Alice",
    response_targets=["Bob", "Charlie"],
    response_type="broadcast",
    payload="[TEAM ONLY] Discuss strategy with your teammates",
)
```

### Pattern 2: Structured Response Requests

```python
# Force specific response format
await self.step_player(
    player_name,
    payload="""
Choose your action for this turn.

Your response MUST end with one of:
- "I choose: ATTACK"
- "I choose: DEFEND"
- "I choose: HEAL"
""",
)
```

### Pattern 3: Injecting Game State

```python
# Give agent current state
await self.step_gamemaster(payload=f"""
=== ROUND {self.round_number} ===

Current standings:
{self.format_scores()}

Remaining items: {self.remaining_items}

Decide who should go next and set the next challenge.
""")
```

### Pattern 4: Tool Result Processing

```python
# Step agent with tools, process results
await self.step_gamemaster(payload="""
Use score_points to award points to the winner.
Then announce the results.
""")

# The tool modifies game state directly via callback
# You can check state after the step returns
print(f"Updated scores: {self.scores}")
```

### Pattern 5: Message Buffering

Messages sent to an agent accumulate in their buffer until they're stepped:

```python
# These all go into Alice's buffer
await self.swarm.submit_message_nowait(msg_from_bob)
await self.swarm.submit_message_nowait(msg_from_charlie)
await self.swarm.submit_message_nowait(msg_from_david)

# When we step Alice, she sees all buffered messages + payload
await self.step_player("Alice", payload="Respond to everyone above")
```

---

## Tips and Best Practices

### 1. Always await_queue_empty() before manual_step()
```python
await self.swarm.await_queue_empty()  # Ensure clean state
response = await self.swarm.manual_step(...)
```

### 2. Use payload for phase-specific instructions
The payload is your control channel. Use it to:
- Tell agents what phase they're in
- Specify required response formats
- Inject current game state
- Give role-specific secret information

### 3. Use dynamic_ctx_ratio for long games
```python
# Compress to 75% to save tokens in long games
await self.swarm.manual_step(
    ...,
    dynamic_ctx_ratio=0.75,
)
```

### 4. Override system prompts for special situations
```python
# Temporarily change agent behavior
await self.swarm.manual_step(
    target="Alice",
    _system="You are now being interrogated. Answer truthfully.",
    payload="What did you do last night?",
)
```

### 5. Design tools that return informative messages
```python
async def score_points(game, args):
    # Return message helps the agent understand what happened
    return f"Awarded {points} to {player}. New total: {game.scores[player]}"
```

### 6. Handle tool errors gracefully
```python
class NarratorError(Exception):
    """Tool validation error - message goes back to agent."""
    pass

async def my_tool(game, args):
    if not valid_target(args["target"]):
        raise NarratorError(f"Invalid target: {args['target']}")
    # ... rest of logic
```

### 7. Use unique task_id per game session
```python
@dataclass
class Game:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
```

### 8. Consider adding interactive mode for debugging
```python
def _interactive_wait(self, agent_name: str, payload: str) -> str:
    if self.interactive:
        print(f"About to step: {agent_name}")
        print(f"Payload: {payload}")
        extra = input("Additional payload (or Enter to continue): ")
        return extra
    return ""
```

---

## Summary

Building games with manual MAIL stepping involves:

1. **Define game state** in a dataclass
2. **Create agent templates** for each player/role
3. **Define actions** as Pydantic models + async functions
4. **Build and instantiate** the swarm in manual mode
5. **Write stepping helpers** that wrap `manual_step`
6. **Implement the game loop** using your stepping helpers
7. **Use payload injection** to control agent behavior per phase
8. **Use response_targets** to control who hears what

The Mafia example demonstrates all these patterns in a complex, multi-phase game with hidden roles, private communication, and sophisticated state management.

---

## Quick Reference

```python
# Initialize
template = MAILSwarmTemplate(name="game", agents=[...], ...)
swarm = template.instantiate({...}, "GameID")
asyncio.create_task(swarm.run_continuous(mode="manual"))

# Send initial message
msg = swarm.build_message(subject="init", body="...", targets=["all"], ...)
await swarm.submit_message_nowait(msg)

# Step an agent
await swarm.await_queue_empty()
response = await swarm.manual_step(
    task_id="...",
    target="AgentName",
    response_targets=["all"] or ["specific", "agents"],
    response_type="broadcast" or "response",
    payload="Phase instructions here",
)

# Define tools
class MyToolArgs(BaseModel):
    arg1: str = Field(description="...")

async def my_tool(game: Game, args: dict) -> str:
    # Modify game state
    return "Result message"

action = MAILAction.from_pydantic_model(
    model=MyToolArgs,
    function=partial(my_tool, game),
    name="my_tool",
)
```

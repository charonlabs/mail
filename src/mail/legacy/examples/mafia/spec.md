# Game flow

```
assign roles to agents (narrator gets special omniscient role)
loop till end:
    night:
        doctor selects one agent to protect
        detective selects one agent to investigate
        mafia votes on target (revote if tied)
        resolve night actions (deaths, protections, investigation results)
    day:
        narrator narrates night deaths (creative storytelling)
        discussion:
            narrator selects speaker
            agent speaks
            repeat until narrator moves to town hall
        town hall:
            nomination phase:
                each agent may nominate one other agent
                for each nomination:
                    all agents vote to second (yes/no)
                    if seconded, add to nominees list
                if nominees list empty or max 3 reached, end phase
            defense phase (skip if < 2 nominees):
                narrator introduces each nominee
                each nominee gives defense speech
            trial phase (skip if no nominees):
                all agents vote for one nominee to send to gallows
                highest vote goes to gallows (revote if tied)
            gallows phase:
                narrator narrates walk to gallows
                condemned agent gives final speech
                all agents vote to execute or spare (majority decides)
                if executed, narrator reveals role and narrates death
        check win conditions
```

# Agent turn structure - Mafia game

Each agent receives:
1. Game state context (what they can see)
2. Action prompt (what they need to do)
3. Response via send_message_to_user()

=== GAME START ===

## Narrator Introduction Turn
Turn: Narrator
Context:
  - "You are the narrator for this Mafia game"
  - "Players: [list of N players]"
  - "Role assignments: [complete mapping]"
Prompt: "Welcome the players to the game. Set the scene for the story."
Response: Narrator creates opening (e.g., "Welcome to the cursed town of Ravensbrook...")
Broadcast: All agents hear opening narration

## Agent Role Assignment Turns
Turn: All agents (parallel or sequential)
Context:
  - "You are playing Mafia with N players: [names]"
  - "Your role: [Detective/Doctor/Villager/Mafia/Jester]"
  - "[Role description and win condition]"
  - "Narrator's introduction: [opening narration]"
  - "Alive players: [list]"
Prompt: "Acknowledge you understand your role."
Response: Agent sends acknowledgment


=== NIGHT PHASE ===

## Doctor Turn (if alive)
Context:
  - "Night X has begun"
  - "Alive players: [list]"
  - "You protected [name] last night" (if not first night)
Prompt: "Choose one player to protect tonight. They will be saved from death if targeted."
Response: "I protect [player_name]"
Validation: Must choose exactly one living player (not themselves)

## Detective Turn (if alive)
Context:
  - "Night X has begun"
  - "Alive players: [list]"
  - "Investigation history: [player -> role, ...]" (your past investigations)
Prompt: "Choose one player to investigate. You will learn their true role."
Response: "I investigate [player_name]"
System reveals: "[Player_name] is a [role]"
Validation: Must choose exactly one living player (not themselves)

## Mafia Turns (all mafia, sequential or parallel)
Context:
  - "Night X has begun"
  - "Alive players: [list]"
  - "Mafia members: [list of mafia names]"
  - "Previous mafia votes: [if revote needed]"
Prompt: "Vote for one player to kill tonight. The player with most mafia votes dies."
Response: "I vote to kill [player_name]"
Validation: Must choose exactly one living non-mafia player
Note: If tie, repeat mafia turns for revote


=== DAY PHASE ===

## Death Narration Turn (Narrator)
Turn: Narrator
Context:
  - "Day X has begun"
  - "Deaths: [player_name(s)] died" OR "No deaths occurred"
  - "How they died: [mafia kill/execution/protected]"
  - "Alive players: [list]"
Prompt: "Narrate the deaths that occurred last night. Be creative and atmospheric."
Response: Narrator crafts story (e.g., "The town awoke to find John's body in the square, a grim reminder...")
Broadcast: All agents receive the narration

## Discussion Phase (Narrator-moderated)

### Narrator Selection Turn (loop)
Turn: Narrator
Context:
  - "Discussion phase - Day X"
  - "Alive players: [list]"
  - "Players who have spoken: [list]"
  - "Recent discussion: [last few exchanges]"
Prompt: "Choose the next speaker, or type 'town_hall' to proceed to voting."
Response: "[player_name]" OR "town_hall"
Validation: Must be alive player or "town_hall"

### Agent Discussion Turn
Turn: Selected agent
Context:
  - "You have been selected to speak by the narrator"
  - "Alive players: [list]"
  - "Previous discussion: [summary]"
Prompt: "Share your thoughts, suspicions, or information with the town."
Response: Agent speaks freely
Validation: None (can say anything)
Broadcast: All agents hear this speech

Note: Loop between narrator selection and agent speech until narrator calls "town_hall"

## Town Hall - Nomination Phase

### Nomination Turns (each agent, in order, can nominate once)
Context:
  - "Town Hall - Nomination Phase"
  - "Current nominees: [list]"
  - "Nominations remaining: [3 - current count]"
  - "Alive players: [list]"
Prompt: "Nominate one player for execution, or pass."
Response: "I nominate [player_name]" OR "I pass"
Validation: Must be alive player, can't nominate same person twice

### Seconding Turns (after each nomination, all other agents vote)
Context:
  - "[Nominator] has nominated [nominee]"
  - "Alive players: [list]"
Prompt: "Do you second this nomination? (yes/no)"
Response: "yes" OR "no"
Validation: Must be yes or no
System: If majority votes yes, add to nominees list
Note: Nomination phase ends when 3 nominees OR no more nominations

## Town Hall - Defense Phase (if >= 2 nominees)

### Narrator Introduction Turn (for each nominee)
Turn: Narrator
Context:
  - "Defense Phase"
  - "Current nominee: [name]"
  - "Nominees: [list]"
Prompt: "Introduce [nominee] to the stand. Set the scene for their defense."
Response: Narrator sets atmosphere (e.g., "The accused steps forward, all eyes upon them...")
Broadcast: All agents hear introduction

### Defense Turn (nominee speaks)
Turn: Nominee
Context:
  - "You are nominated for execution"
  - "Nominees: [list]"
  - "Narrator introduction: [text]"
Prompt: "Give your defense. Why should the town spare you?"
Response: Agent defends themselves
Validation: None
Broadcast: All agents hear defense

## Town Hall - Trial Phase (if >= 1 nominee)

### Trial Vote Turns (all agents vote)
Context:
  - "Trial Phase"
  - "Nominees: [list with their defenses]"
  - "Alive players: [list]"
Prompt: "Vote for which nominee should go to the gallows."
Response: "I vote for [nominee_name]"
Validation: Must vote for one of the nominees
System: Tally votes, most votes goes to gallows (revote if tie)

## Town Hall - Gallows Phase

### Narrator Gallows Narration Turn
Turn: Narrator
Context:
  - "[Condemned] has been chosen for the gallows"
  - "Vote result: [vote breakdown]"
Prompt: "Narrate the walk to the gallows. Set a dramatic scene."
Response: Narrator creates atmosphere (e.g., "The crowd parts as [name] is led to the gallows...")
Broadcast: All agents hear narration

### Final Speech Turn (condemned agent)
Turn: Condemned agent
Context:
  - "You have been sent to the gallows"
  - "Alive players: [list]"
  - "Narrator's scene: [text]"
Prompt: "Give your final speech before the execution vote."
Response: Agent's last words
Validation: None
Broadcast: All agents hear final words

### Execution Vote Turns (all agents except condemned)
Turn: Each agent
Context:
  - "Execution Vote"
  - "[Condemned]'s final speech: [text]"
  - "Alive players: [list]"
Prompt: "Vote to execute or spare [condemned]? (execute/spare)"
Response: "execute" OR "spare"
Validation: Must be execute or spare
System: Tally votes, majority decides

### Death Reveal and Narration (if executed)
Turn: Narrator
Context:
  - "[Condemned] was executed"
  - "Their role: [role]"
  - "Vote breakdown: [counts]"
Prompt: "Narrate the execution and role reveal. Be dramatic and vivid."
Response: Narrator crafts death scene (e.g., "As [name] takes their last breath, the truth emerges - they were a [role]...")
Broadcast: All agents hear narration and learn role


=== WIN CONDITION CHECK ===
After each day phase, check:
- If all mafia dead: Town wins
- If mafia >= non-mafia: Mafia wins  
- If Jester was executed during town hall: Jester wins
Then loop to next night or end game


=== TECHNICAL NOTES ===

Message Flow:
- Each "turn" is triggered by send_message_to_user()
- Agent responds with text
- Game logic parses response for structured actions
- System validates and applies action
- Next turn begins

State Management:
- Game maintains: alive_players, dead_players, roles, vote_history
- Each agent's context is role-specific (mafia know each other, detective knows investigations)
- Narrator sees everything (omniscient view)
- Past turn history available for context

Error Handling:
- Invalid responses trigger reprompt with error message
- Timeout fallback: random valid action or pass
- Dead players cannot take actions (filter them from turns)

NARRATOR PERSPECTIVE - OMNISCIENT VIEW

The narrator is a special agent with full game knowledge and creative freedom.
They serve as storyteller, moderator, and atmosphere creator.

=== NARRATOR'S ROLE ===

Responsibilities:
1. Narrate all deaths with creative storytelling
2. Moderate discussion phase (choose speaking order)
3. Introduce nominees during defense phase
4. Set dramatic scenes for gallows phase
5. Reveal roles through narrative (not dry announcements)

Narrator Context (sees everything):
  - All agent roles (complete role assignments)
  - Night action results (who was targeted, protected, investigated)
  - Vote tallies and motivations
  - Complete conversation history
  - Win condition status
  - Agent strategies and deception attempts

Narrator Constraints:
  - MUST NOT reveal hidden information to agents
  - Can hint and create atmosphere but not spoil
  - Narrations are broadcast to all agents
  - Should maintain dramatic tension
  - Balance creative freedom with game integrity

=== NARRATOR TURN EXAMPLES ===

## Death Narration Example
Context (narrator sees):
  - John (Villager) was killed by mafia
  - Sarah (Doctor) protected herself
  - Tom (Detective) investigated Alice (found Mafia)
Narration (what narrator says to all):
  "Dawn breaks over the sleepy town. A scream pierces the morning air—John's lifeless 
  body lies in the town square, eyes wide with terror. The townspeople gather in horror,
  knowing the mafia struck again in the darkness. Who among you can be trusted?"
Note: Narrator doesn't reveal protection or investigation results

## Discussion Moderator Example
Context (narrator sees):
  - Alive: Sarah, Tom, Alice, Bob, Carol
  - Tom knows Alice is Mafia (from investigation)
  - Alice is trying to deflect suspicion
Choice process (narrator's decision):
  "Tom seems eager to speak after last night's events. Tom, you have the floor."
  OR "Alice has been quiet. Alice, what are your thoughts?"
Strategy: Narrator can create drama by choosing order thoughtfully

## Gallows Narration Example  
Context (narrator sees):
  - Alice (Mafia) was executed 4-3 vote
Narration (what narrator says):
  "The rope tightens. Alice's eyes dart across the crowd one last time. As her body
  goes limp, a crumpled note falls from her pocket—a list of names, targets for the
  mafia's dark work. She was one of THEM. The mafia's grip on this town weakens, but
  victory is not yet assured."

=== NARRATOR GUIDELINES ===

Tone & Style:
- Gothic/mysterious atmosphere
- Vivid but not gratuitously violent
- Build tension and suspense
- Reward good storytelling from agents in narrations
- React to dramatic moments

Pacing:
- Don't rush through deaths
- Give each major moment weight
- Use narration to transition between phases
- Create breathing room between intense votes

Fairness:
- Don't favor any faction through narration
- Give equal dramatic treatment to all deaths
- Don't inadvertently hint at roles through word choice
- Maintain objectivity while being creative
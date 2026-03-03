from dataclasses import dataclass, field
from typing import Any


@dataclass
class Role:
    name: str
    bio: str
    wincon: str
    power: int
    abilities: list[Any] = field(default_factory=list)


TOWN_ROLES = {
    "Doctor": Role(
        name="Doctor",
        bio="A doctor who can protect one person per night, saving them from death if they are targeted that same night.",
        wincon="As a member of the town, you win if all mafia members are killed.",
        power=2,
        abilities=["protect"],
    ),
    "Detective": Role(
        name="Detective",
        bio="A detective who can investigate one person per night, revealing their role to you.",
        wincon="As a member of the town, you win if all mafia members are killed.",
        power=2,
        abilities=["investigate"],
    ),
    "Villager": Role(
        name="Villager",
        bio="A normal townsperson with no special abilities.",
        wincon="As a member of the town, you win if all mafia members are killed.",
        power=0,
    ),
}

MAFIA_ROLES = {
    "Mafia": Role(
        name="Mafia",
        bio="A mafia member who can point to one person per night to vote for them to be killed. The person with the most votes from mafia members is killed that night.",
        wincon="As a member of the mafia, you win if you kill all non-mafia town members.",
        power=4,
        abilities=["vote"],
    )
}

NEUTRAL_ROLES = {
    "Jester": Role(
        name="Jester",
        bio="A town jester who has no special abilities, but a special win condition.",
        wincon="As the town jester, you win if the town votes for you to be killed during a town hall session.",
        power=2,
    ),
}

ALL_ROLES = {**TOWN_ROLES, **MAFIA_ROLES, **NEUTRAL_ROLES}


def choose_faction_counts(n: int) -> tuple[int, int, int]:
    """
    Choose the number of town, mafia, and neutral roles to use in the game, based on the total number of players.

    :param n: The total number of players in the game.
    :return: A tuple containing the number of town, mafia, and neutral roles to use in the game.
    """
    mafia = max(1, round(n * 0.3))

    if n < 8:
        neutral = 0
    elif n < 12:
        neutral = 1
    else:
        neutral = 1 + (n - 12) // 6

    town = n - mafia - neutral

    return town, mafia, neutral


def choose_power_budgets(town: int, mafia: int, neutral: int) -> tuple[int, int, int]:
    """
    Choose the power budgets for the town, mafia, and neutral roles, based on the number of players in each faction.

    :param town: The number of town players in the game.
    :param mafia: The number of mafia players in the game.
    :param neutral: The number of neutral players in the game.
    :return: A tuple containing the power budgets for the town, mafia, and neutral roles.
    """
    town_frac = min(1, 0.8 + 0.01 * town)
    mafia_frac = min(0.5, 0.3 + 0.02 * mafia)

    town_budget = round(town * town_frac)
    mafia_budget = round(mafia * mafia_frac)
    neutral_budget = neutral

    print(
        f"Town budget: {town_budget}, Mafia budget: {mafia_budget}, Neutral budget: {neutral_budget}"
    )

    return town_budget, mafia_budget, neutral_budget


def allocate_town_roles(town: int, town_budget: int) -> dict[str, int]:
    """
    Allocate individual counts of town roles, based on the number of players in the town and the power budget.

    :param town: The number of town players in the game.
    :param town_budget: The power budget for the town.
    :return: A dictionary mapping the role names to their counts.
    """
    roles = {role.name: 0 for role in TOWN_ROLES.values()}
    remaining_budget = town_budget
    town_power_roles = [role for role in TOWN_ROLES.values() if role.power > 1]
    for role in town_power_roles:
        while remaining_budget >= role.power:
            max_copies = 1 if town <= 7 else 2
            if roles[role.name] >= max_copies:
                break
            roles[role.name] += 1
            remaining_budget -= role.power

    used_slots = sum(roles.values())
    roles["Villager"] = max(0, town - used_slots)
    return roles


def calculate_roles(n: int) -> dict[str, int]:
    """
    Calculate the number of each role to use in the game, based on the total number of players.

    :param n: The total number of players in the game.
    :return: A dictionary mapping the role names to their counts.
    """
    town, mafia, neutral = choose_faction_counts(n)
    town_budget, mafia_budget, neutral_budget = choose_power_budgets(
        town, mafia, neutral
    )

    town_roles = allocate_town_roles(town, town_budget)
    mafia_roles = {"Mafia": mafia}
    neutral_roles = {"Jester": neutral}
    final_roles: dict[str, int] = {}
    for d in (town_roles, mafia_roles, neutral_roles):
        for role, count in d.items():
            if count > 0:
                final_roles[role] = final_roles.get(role, 0) + count
    return final_roles

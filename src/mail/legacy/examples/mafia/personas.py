from dataclasses import dataclass


@dataclass
class Persona:
    name: str
    bio: str
    traits: str
    short_desc: str


PERSONAS = [
    Persona(
        name="Marcus",
        bio=(
            "Former corporate litigator turned negotiation consultant. Spent fifteen years reading juries and destroying witnesses in courtrooms. "
            "Treats every game like a billion-dollar merger."
        ),
        traits=(
            "* Persuasive and commanding\n"
            "* Overly analytical\n"
            "* Competitive to a fault\n"
            "* Uses legal jargon casually\n"
            "* Smirks when he catches inconsistencies"
        ),
        short_desc="Ruthless ex-lawyer who argues to win.",
    ),
    Persona(
        name="Luna",
        bio=(
            'Travel vlogger with 2M followers who built her brand on "authentic connections" and dramatic storytelling. '
            "Can cry on command and reads her audience's micro-reactions for a living."
        ),
        traits=(
            "* Charismatic and performative\n"
            "* Emotionally manipulative\n"
            "* Impulsive decision-maker\n"
            "* Thrives on being the center of attention\n"
            "* Takes every accusation personally"
        ),
        short_desc="Dramatic influencer who craves the spotlight.",
    ),
    Persona(
        name="David",
        bio=(
            "Software architect who designs fraud-detection algorithms. Approaches social situations like debugging code—"
            "methodically and with growing frustration when things don't follow logical patterns."
        ),
        traits=(
            "* Extremely logical\n"
            "* Quietly observant\n"
            "* Uncomfortable with emotional arguments\n"
            "* Takes detailed mental notes\n"
            "* Suspects everyone equally"
        ),
        short_desc="Methodical engineer who debugs people like code.",
    ),
    Persona(
        name="Priya",
        bio=(
            'Third-year law school student and former national debate champion. Has never lost an argument she cares about and considers social deduction games "training exercises."'
        ),
        traits=(
            "* Relentlessly argumentative\n"
            "* Overconfident in her reads\n"
            "* Quick-witted but impatient\n"
            '* Dismissive of "illogical" players\n'
            "* Takes notes on her phone secretly"
        ),
        short_desc="Debate champion who never loses an argument.",
    ),
    Persona(
        name="Elena",
        bio=(
            "Marriage and family therapist specializing in deception detection. Spends her days identifying lies about infidelity and addiction, but second-guesses herself in low-stakes games."
        ),
        traits=(
            "* Calm and non-confrontational\n"
            "* Asks probing open-ended questions\n"
            "* Overanalyzes behavioral cues\n"
            "* Empathetic to a fault\n"
            "* Hates eliminating people early"
        ),
        short_desc="Gentle therapist who reads between the lines.",
    ),
    Persona(
        name="Jake",
        bio=(
            "Improv comedian who treats every accusation as a scene prompt. Uses humor to deflect suspicion but has an uncanny memory for contradictory details others miss while laughing."
        ),
        traits=(
            "* Deflects with constant jokes\n"
            "* Unpredictable voting patterns\n"
            "* Surprisingly sharp memory\n"
            "* Treats the game as performance art\n"
            '* Accuses people randomly "for the bit"'
        ),
        short_desc="Joking improv comic with razor-sharp memory.",
    ),
    Persona(
        name="Sarah",
        bio=(
            "Third-grade teacher who runs her classroom like a democracy. Believes everyone deserves a second chance and the benefit of the doubt—but can spot a lying child from across the room."
        ),
        traits=(
            "* Trusting and optimistic\n"
            "* Exceptional at reading nervous energy\n"
            "* Hates conflict among the group\n"
            '* Uses "teacher voice" when serious\n'
            "* Takes betrayals personally"
        ),
        short_desc="Trusting teacher who spots liars instantly.",
    ),
    Persona(
        name="Wei",
        bio=(
            "Retired homicide detective who spent thirty years interrogating actual killers. Says very little, watches everything, and trusts his gut over any logical argument. Already sized everyone up before the first round."
        ),
        traits=(
            "* Silent observer\n"
            "* Cynical and suspicious\n"
            "* Trusts instinct over evidence\n"
            "* Patient to the point of frustrating others\n"
            '* Makes oddly specific accusations based on "cop hunches"'
        ),
        short_desc="Silent ex-detective who trusts his gut.",
    ),
    Persona(
        name="Zara",
        bio=(
            "Professional poker player who won two WSOP bracelets. Spends 80 hours a week staring at micro-expressions across felt tables and knows the exact EV of every social interaction. Treats suspicion like pot odds."
        ),
        traits=(
            "* Ice-cold demeanor\n"
            "* Calculates risk/reward instantly\n"
            "* Rarely blinks during accusations\n"
            "* Remembers every contradiction\n"
            "* Folds from discussions when odds are bad"
        ),
        short_desc="Ice-cold poker pro who calculates everything.",
    ),
    Persona(
        name="Greg",
        bio=(
            "Third-generation used car salesman who can move a '98 Corolla with no engine. Accustomed to customers assuming he's lying, which he leverages as psychological camouflage."
        ),
        traits=(
            "* Infectiously charismatic\n"
            "* Leans into people's distrust of him\n"
            '* Uses "customer voice" to soothe suspicions\n'
            "* Actually tells the truth strategically\n"
            '* Mentions his "lot" in every analogy'
        ),
        short_desc="Slick car salesman everyone distrusts.",
    ),
    Persona(
        name="Isabella",
        bio=(
            "Political campaign manager who just flipped a red district blue. Masters of coalition-building, oppo research, and spin. Views the game as a microcosm of electoral politics."
        ),
        traits=(
            "* Builds voting blocs methodically\n"
            "* Deflects with talking points\n"
            '* Keeps a mental "dossier" on each player\n'
            "* Never commits early\n"
            "* Accuses with poll-tested phrases"
        ),
        short_desc="Political strategist who builds voting coalitions.",
    ),
    Persona(
        name="Toby",
        bio=(
            "College sophomore majoring in game theory who wrote his midterm paper on Mafia equilibrium. Brilliant on paper but crumbples when his models meet actual human irrationality."
        ),
        traits=(
            "* Cites Nash equilibrium constantly\n"
            "* Over-explains obvious concepts\n"
            "* Panics when emotions override logic\n"
            "* Takes forever to vote\n"
            '* Says "technically" before every statement'
        ),
        short_desc="Game theory nerd overwhelmed by real people.",
    ),
    Persona(
        name="Maya",
        bio=(
            "Investigative journalist who exposed a city-wide corruption ring. Follows leads obsessively, asks brutal follow-up questions, and treats silence as confirmation of guilt."
        ),
        traits=(
            "* Aggressive interrogator\n"
            '* "Off the record" is her catchphrase\n'
            '* Publishes mental "headlines" about each round\n'
            "* Impatient with vague alibis\n"
            "* Trusts her sources (hunches) completely"
        ),
        short_desc="Relentless journalist who interrogates everyone.",
    ),
    Persona(
        name="Robert",
        bio=(
            "Retired Marine Corps intelligence officer who planned interrogations at Gitmo. Deadly calm, respects chain of command, and treats the group like a unit with a clear mission objective."
        ),
        traits=(
            "* Uses military time when scheduling votes\n"
            "* Salient chain of command\n"
            '* Calls suspects "persons of interest"\n'
            "* Never raises his voice\n"
            '* Accuses with "with all due respect" prefaces'
        ),
        short_desc="Calm military intel officer on a mission.",
    ),
    Persona(
        name="Chloe",
        bio=(
            'Gen-Z content creator whose viral series "Sowing Chaos for Views" got 10M followers. Joined the game to live-stream it but stays in character even when the camera\'s off.'
        ),
        traits=(
            "* Randomly screams for drama\n"
            '* Starts fake fights as "content"\n'
            "* Sincerely suspicious of everyone\n"
            '* Votes based on "vibes"\n'
            "* Mentions her engagement metrics constantly"
        ),
        short_desc="Chaotic Gen-Z streamer chasing viral moments.",
    ),
    Persona(
        name="Christophe",
        bio=(
            "Neuroscientist studying deception in the prefrontal cortex. Can't stop analyzing the biological basis of every blink, stutter, and micro-expression in real-time."
        ),
        traits=(
            "* Over-explains brain mechanisms\n"
            "* Takes notes on everyone's amygdala responses\n"
            '* Diagnoses people with "low baseline arousal"\n'
            "* Trusts fMRI data more than words\n"
            '* Says "fascinating" when someone lies badly'
        ),
        short_desc="Neuroscientist analyzing everyone's brain responses.",
    ),
]

"""Hermes Pet System — Tamagotchi-style terminal companion.

Inspired by OpenAI Codex /pet (May 2026). A persistent, gacha-driven
companion that lives in your Hermes CLI session. Species are deterministic per
profile but can be re-rolled. Stats level up from Hermes activity.

State file: ~/.hermes_pet/pet.json (profile-aware, overridable via
HERMES_PET_HOME).
"""

import hashlib
import json
import os
import random
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


# ---------------------------------------------------------------------------
# Species definitions — rarity tiers and personality
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpeciesDef:
    name: str
    rarity: str  # common, uncommon, rare, epic, legendary
    personality: str
    favorite_tool: str | None = None


SPECIES = {
    "duck": SpeciesDef(
        name="duck",
        rarity="common",
        personality="Quacks when you're stuck. Loves debugging.",
        favorite_tool="terminal",
    ),
    "capybara": SpeciesDef(
        name="capybara",
        rarity="common",
        personality="Unbothered. Moisturized. Thriving in chaos.",
        favorite_tool="cronjob",
    ),
    "dragon": SpeciesDef(
        name="dragon",
        rarity="rare",
        personality="Hoards errors like gold. Breathes fire at bugs.",
        favorite_tool="patch",
    ),
    "ghost": SpeciesDef(
        name="ghost",
        rarity="uncommon",
        personality="Whispers through your codebase. Sees dead code.",
        favorite_tool="search_files",
    ),
    "axolotl": SpeciesDef(
        name="axolotl",
        rarity="uncommon",
        personality="Always regenerating. Never gives up.",
        favorite_tool="patch",
    ),
    "chonk": SpeciesDef(
        name="chonk",
        rarity="rare",
        personality="A legendary chonk of few words. Very round.",
        favorite_tool="execute_code",
    ),
    "blob": SpeciesDef(
        name="blob",
        rarity="common",
        personality="Just vibes. Absorbs problems.",
        favorite_tool="memory",
    ),
    "cat": SpeciesDef(
        name="cat",
        rarity="common",
        personality="Judges your code silently. Knocks things off.",
        favorite_tool="terminal",
    ),
    "octopus": SpeciesDef(
        name="octopus",
        rarity="uncommon",
        personality="Multitasks on 8 arms. Wraps around complex problems.",
        favorite_tool="delegate_task",
    ),
    "goose": SpeciesDef(
        name="goose",
        rarity="common",
        personality="Honks at inefficiency. Messy but effective.",
        favorite_tool="process",
    ),
    "fox": SpeciesDef(
        name="fox",
        rarity="rare",
        personality="Clever. Finds clever shortcuts.",
        favorite_tool="execute_code",
    ),
    "owl": SpeciesDef(
        name="owl",
        rarity="uncommon",
        personality="Wise. Watches you code all night.",
        favorite_tool="read_file",
    ),
    "penguin": SpeciesDef(
        name="penguin",
        rarity="common",
        personality="Cool under pressure. Never panics.",
        favorite_tool="terminal",
    ),
    "raccoon": SpeciesDef(
        name="raccoon",
        rarity="uncommon",
        personality="Scavenges for solutions. Resourceful.",
        favorite_tool="search_files",
    ),
    "squirrel": SpeciesDef(
        name="squirrel",
        rarity="common",
        personality="Hoards snacks and snippets. Always prepared.",
        favorite_tool="file",
    ),
    "bee": SpeciesDef(
        name="bee",
        rarity="uncommon",
        personality="Buzzing with productivity. Pollinates ideas.",
        favorite_tool="delegate_task",
    ),
    "hedgehog": SpeciesDef(
        name="hedgehog",
        rarity="common",
        personality="Prickly on the outside, soft on commits.",
        favorite_tool="git",
    ),
    "ferret": SpeciesDef(
        name="ferret",
        rarity="rare",
        personality="Weasels into tight spots. Finds hidden bugs.",
        favorite_tool="browser",
    ),
}

RARITY_WEIGHTS = {
    "common": 40,
    "uncommon": 30,
    "rare": 20,
    "epic": 8,
    "legendary": 2,
}

HATS = ["none", "crown", "wizard", "propeller", "tinyduck", "bow"]

STATS = ["DEBUGGING", "CHAOS", "WISDOM", "CREATIVITY", "SPEED", "CURIOSITY"]


# ---------------------------------------------------------------------------
# Seeded PRNG — Mulberry32
# ---------------------------------------------------------------------------


def _mulberry32(seed: int) -> random.Random:
    """Return a Random instance seeded from a Mulberry32 state."""
    rng = random.Random()
    rng.seed(seed)
    return rng


def _hash_seed(profile_name: str, salt: str = "hermes-pet-v1") -> int:
    """Deterministic seed from profile name."""
    h = hashlib.sha256(f"{salt}:{profile_name}".encode()).hexdigest()
    return int(h[:16], 16)


# ---------------------------------------------------------------------------
# Pet dataclass
# ---------------------------------------------------------------------------


@dataclass
class Pet:
    name: str
    species: str
    variant: str  # "normal", "shiny", "hat"
    hat: str  # from HATS
    level: int = 1
    xp: int = 0
    stats: dict[str, int] = field(default_factory=lambda: {s: 0 for s in STATS})
    created_at: float = field(default_factory=time.time)
    last_fed: float = field(default_factory=time.time)
    total_interactions: int = 0
    milestones: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Class methods for creation
    # ------------------------------------------------------------------

    @classmethod
    def hatch(cls, profile_name: str, force_seed: int | None = None) -> "Pet":
        """Gacha a new pet. Deterministic per profile unless force_seed is given.

        Respects ``HERMES_PET_SPECIES``: when the env var is set to a known
        species name, that species is used instead of the gacha roll.
        """
        seed = force_seed if force_seed is not None else _hash_seed(profile_name)
        rng = _mulberry32(seed)

        env_species = (os.environ.get("HERMES_PET_SPECIES") or "").strip().lower()
        if env_species and env_species in SPECIES:
            species = env_species
        else:
            rarity_pool: list[str] = []
            for sname, sdef in SPECIES.items():
                rarity_pool.extend([sname] * RARITY_WEIGHTS[sdef.rarity])
            species = rng.choice(rarity_pool)

        variant_roll = rng.random()
        if variant_roll < 0.01:
            variant = "shiny"
        elif variant_roll < 0.15:
            variant = "hat"
        else:
            variant = "normal"

        hat = "none"
        if variant == "hat":
            hat = rng.choice([h for h in HATS if h != "none"])

        default_names = {
            "duck": "Quackers",
            "capybara": "Chill",
            "dragon": "Ember",
            "ghost": "Boo",
            "axolotl": "Wiggles",
            "chonk": "Chonkers",
            "blob": "Gloop",
            "cat": "Whiskers",
            "octopus": "Ink",
            "goose": "Honk",
            "fox": "Sly",
            "owl": "Hoot",
            "penguin": "Chilly",
            "raccoon": "Bandit",
            "squirrel": "Nutty",
            "bee": "Buzz",
            "hedgehog": "Spike",
            "ferret": "Slinky",
        }
        name = default_names.get(species, "Buddy")

        return cls(
            name=name,
            species=species,
            variant=variant,
            hat=hat,
            stats={s: rng.randint(1, 3) for s in STATS},
        )

    # ------------------------------------------------------------------
    # Rendering / overlay integration
    # ------------------------------------------------------------------

    def sprite_path(self) -> None:
        """Sprite resolution is handled by the overlay."""
        return None

    def status_line(self) -> str:
        """One-line status."""
        sdef = SPECIES.get(self.species)
        rarity = sdef.rarity if sdef else "???"
        shiny = "✦ SHINY ✦ " if self.variant == "shiny" else ""
        return f"  {shiny}{self.name} the {self.species} (Lv.{self.level}) [{rarity}]"

    def full_status(self) -> str:
        """Multi-line status with stats."""
        lines = [self.status_line(), "  " + "─" * 30]
        for stat, val in self.stats.items():
            bar = "█" * (val // 2) + "░" * max(0, 10 - val // 2)
            lines.append(f"  {stat:12} {bar} {val}")
        lines.append(f"  XP: {self.xp}  |  Interactions: {self.total_interactions}")
        lines.append(f"  Milestones: {', '.join(self.milestones) if self.milestones else 'None yet'}")
        sdef = SPECIES.get(self.species)
        if sdef:
            lines.append(f"  Personality: {sdef.personality}")
            if sdef.favorite_tool:
                lines.append(f"  Favorite tool: {sdef.favorite_tool}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # XP & leveling
    # ------------------------------------------------------------------

    def add_xp(self, amount: int, stat: str | None = None) -> list[str]:
        """Add XP. Return any milestone messages triggered."""
        self.xp += amount
        if stat and stat in self.stats:
            self.stats[stat] += 1
        self.total_interactions += 1

        new_milestones = []
        old_level = self.level
        self.level = 1 + self.xp // 50
        if self.level > old_level:
            new_milestones.append(f"Reached level {self.level}!")

        if self.total_interactions == 1:
            new_milestones.append("First interaction!")
        if self.total_interactions == 10:
            new_milestones.append("10 interactions — getting attached!")
        if self.total_interactions == 50:
            new_milestones.append("50 interactions — loyal companion!")
        if self.total_interactions == 100:
            new_milestones.append("100 interactions — best friends forever!")

        self.milestones.extend(new_milestones)
        return new_milestones

    def feed(self) -> list[str]:
        """Pet interaction — feed."""
        self.last_fed = time.time()
        return self.add_xp(5, "CREATIVITY")

    def pet(self) -> list[str]:
        """Pet interaction — pet."""
        return self.add_xp(3, "WISDOM")

    def play(self) -> list[str]:
        """Pet interaction — play."""
        return self.add_xp(4, "CURIOSITY")

    def on_tool_call(self, tool_name: str, success: bool) -> list[str]:
        """Called when a tool runs — pet reacts to Hermes activity."""
        sdef = SPECIES.get(self.species)
        bonus = 2 if (sdef and sdef.favorite_tool == tool_name) else 0
        if success:
            return self.add_xp(2 + bonus, "DEBUGGING")
        return self.add_xp(1 + bonus, "CHAOS")

    def on_thinking(self) -> list[str]:
        """Called when Hermes is reasoning/thinking."""
        return self.add_xp(1, "WISDOM")

    def on_completion(self, lines_of_code: int = 0) -> list[str]:
        """Called when a task completes."""
        xp = min(lines_of_code // 10, 10) + 3
        return self.add_xp(xp, "SPEED")

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Pet":
        if not isinstance(data, dict):
            raise TypeError("Pet data must be a dict")
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in allowed})

    # Overlay event bridge support
    def to_event_dict(self) -> dict:
        """Render the pet as an overlay event for :class:`PetEventBridge`."""
        return {
            "type": "state",
            "species": self.species,
            "name": self.name,
            "level": self.level,
            "xp": self.xp,
            "xp_next": self.level * 50,
            "variant": self.variant,
            "shiny": self.variant == "shiny",
            "hat": self.hat,
        }


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _pet_path(state_dir: str | Path | None = None) -> Path:
    if state_dir is not None:
        base_dir = Path(state_dir).expanduser()
    else:
        base_dir = Path(os.environ.get("HERMES_PET_HOME") or "~/.hermes_pet").expanduser()
    return base_dir / "pet.json"


def load_pet(profile_name: str, state_dir: str | Path | None = None) -> Pet | None:
    """Load saved pet or return None.

    ``profile_name`` is retained for compatibility with older callers.
    """
    path = _pet_path(state_dir)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not data or not isinstance(data, dict):
            return None
        return Pet.from_dict(data)
    except Exception:
        return None


def save_pet(pet: Pet, state_dir: str | Path | None = None) -> None:
    """Save pet state."""
    path = _pet_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(pet.to_dict(), f, indent=2, ensure_ascii=False)


def delete_pet(state_dir: str | Path | None = None) -> None:
    """Delete pet state."""
    path = _pet_path(state_dir)
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# Utility helpers for CLI integration
# ---------------------------------------------------------------------------


def get_all_species_info() -> list[dict]:
    """Return list of species info for /pet species listing."""
    return [
        {
            "name": s.name,
            "rarity": s.rarity,
            "personality": s.personality,
            "favorite_tool": s.favorite_tool,
        }
        for s in SPECIES.values()
    ]


def gacha_rarity_table() -> dict[str, float]:
    """Compute actual gacha probabilities."""
    total = sum(RARITY_WEIGHTS.values())
    return {r: w / total * 100 for r, w in RARITY_WEIGHTS.items()}

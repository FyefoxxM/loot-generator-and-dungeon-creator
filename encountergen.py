#!/usr/bin/env python3
"""
encountergen.py

Data-driven encounter and five-room-dungeon generator.

- JSON-first: all tunable content in JSON files.
- Library-first, CLI-second.
- Deterministic via --seed.
- Uses lootgen.generate_loot(...) for loot parcels.

Standard encounter shape:

{
  "difficulty": <int>,            # target level / CR band
  "type": "combat" | "puzzle" | "social" | "exploration" | "empty",
  "slot": "entrance" | "puzzle" | "setback" | "climax" | "aftermath",
  "biome": "dungeon" | "forest" | ...,
  "enemies": [
    {
      "monster_id": "goblin",
      "name": "Goblin",
      "count": 4,
      "cr": 0.25,
      "faction": "goblin_tribe",
      "tags": ["humanoid", "sneaky"]
    }
  ],
  "environment": {
    "preset_id": "narrow_passage",
    "description": "A cramped stone corridor with low ceiling.",
    "tags": ["tight_quarters"],
    "mechanical_effects": {...}
  },
  "tags": ["ambush", "raiders"],
  "loot": { ... loot.v1 ... } or null,
  "meta": {
    "template_id": "goblins_ambush",
    "noncombat_id": "puzzle_locked_door",
    "notes": ""
  }
}

Five-room dungeon output:

{
  "schema": "dungeon.5room.v1",
  "seed": 1234,
  "biome": "dungeon",
  "base_level": 5,
  "rooms": [
    {
      "slot": "entrance",
      "room_index": 1,
      "encounter": { ... encounter schema ... }
    },
    ...
  ]
}

JSON files expected (names fixed, content is yours):

REQUIRED:
- encounter_types.json          (schema: encounter.types.v1)
- five_room_progression.json    (schema: five.room.progression.v1)
- encounter_tables.json         (schema: encounter.tables.v1)
- enemy_groups.json             (schema: enemy.groups.v1)
- monsters.json                 (schema: monsters.v1)

OPTIONAL (graceful degradation if missing):
- combat_budgets.json           (schema: combat.budgets.v1)
- factions.json                 (schema: factions.v1)
- environment_presets.json      (schema: environment.presets.v1)
- puzzle_tables.json            (schema: puzzle.tables.v1)
- social_tables.json            (schema: social.tables.v1)
- exploration_tables.json       (schema: exploration.tables.v1)

Use:

    from pathlib import Path
    from encountergen import generate_five_room_dungeon

    dungeon = generate_five_room_dungeon(
        base_level=5,
        biome="dungeon",
        seed=1234,
        data_dir=Path("data"),
        loot_data_dir=Path("data"),
        loot_data_file="loot_data.json",
    )

CLI:

    python encountergen.py --level 5 --biome dungeon --seed 1234 \
        --rooms 5 --data-dir data --loot-data-dir data --output dungeon.json
"""

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from lootgen import generate_loot
except ImportError:
    from .lootgen import generate_loot


# --------------------------- JSON loading ------------------------------------


def _load_json(path: Path, required: bool = True) -> Dict[str, Any]:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Required JSON file not found: {path}")
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@dataclass
class Tables:
    encounter_types: Dict[str, Any]
    five_room_progression: Dict[str, Any]
    combat_budgets: Dict[str, Any]
    encounter_templates: Dict[str, Any]
    enemy_groups: Dict[str, Any]
    monsters: Dict[str, Any]
    factions: Dict[str, Any]
    environment_presets: Dict[str, Any]
    puzzle_tables: Dict[str, Any]
    social_tables: Dict[str, Any]
    exploration_tables: Dict[str, Any]

    @classmethod
    def load(cls, data_dir: Optional[Path] = None) -> "Tables":
        if data_dir is None:
            data_dir = Path(__file__).parent
        data_dir = Path(data_dir)

        encounter_types = _load_json(data_dir / "encounter_types.json", required=True)
        five_room_progression = _load_json(
            data_dir / "five_room_progression.json", required=True
        )
        combat_budgets = _load_json(data_dir / "combat_budgets.json", required=False)
        encounter_templates = _load_json(
            data_dir / "encounter_tables.json", required=True
        )
        enemy_groups = _load_json(data_dir / "enemy_groups.json", required=True)
        monsters = _load_json(data_dir / "monsters.json", required=True)
        factions = _load_json(data_dir / "factions.json", required=False)
        environment_presets = _load_json(
            data_dir / "environment_presets.json", required=False
        )
        puzzle_tables = _load_json(
            data_dir / "puzzle_tables.json", required=False
        )
        social_tables = _load_json(
            data_dir / "social_tables.json", required=False
        )
        exploration_tables = _load_json(
            data_dir / "exploration_tables.json", required=False
        )

        return cls(
            encounter_types=encounter_types,
            five_room_progression=five_room_progression,
            combat_budgets=combat_budgets,
            encounter_templates=encounter_templates,
            enemy_groups=enemy_groups,
            monsters=monsters,
            factions=factions,
            environment_presets=environment_presets,
            puzzle_tables=puzzle_tables,
            social_tables=social_tables,
            exploration_tables=exploration_tables,
        )


# --------------------------- utility -----------------------------------------


def _clamp_level(level: int, budgets: Dict[str, Any]) -> int:
    try:
        keys = [int(k) for k in budgets.get("budgets", {}).keys()]
    except Exception:
        keys = []
    if not keys:
        return max(1, level)
    min_lvl = min(keys)
    max_lvl = max(keys)
    if level < min_lvl:
        return min_lvl
    if level > max_lvl:
        return max_lvl
    return level


def _get_budget_for_level(level: int, budgets: Dict[str, Any]) -> Optional[float]:
    b = budgets.get("budgets") or {}
    key = str(level)
    value = b.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _weighted_choice(rng: random.Random, items: List[Tuple[Any, float]]) -> Any:
    total = sum(max(0.0, w) for _, w in items)
    if total <= 0:
        return items[0][0]
    r = rng.random() * total
    acc = 0.0
    for item, weight in items:
        acc += max(0.0, weight)
        if r <= acc:
            return item
    return items[-1][0]


def _index_by_id(items: List[Dict[str, Any]], key: str = "id") -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for it in items:
        id_val = it.get(key)
        if isinstance(id_val, str):
            out[id_val] = it
    return out


# --------------------------- core generator ----------------------------------


class EncounterGenerator:
    def __init__(
        self,
        tables: Tables,
        seed: Optional[int] = None,
        loot_data_dir: Optional[Path] = None,
        loot_data_file: str = "loot_data.json",
    ):
        self.tables = tables
        self.seed = seed if seed is not None else random.randint(0, 999_999)
        self.rng = random.Random(self.seed)
        self.loot_data_dir = loot_data_dir
        self.loot_data_file = loot_data_file

        self._monster_index = _index_by_id(self.tables.monsters.get("monsters", []))
        self._enemy_group_index = _index_by_id(
            self.tables.enemy_groups.get("groups", []), key="id"
        )
        self._faction_index = _index_by_id(
            self.tables.factions.get("factions", []), key="id"
        )
        self._env_index = _index_by_id(
            self.tables.environment_presets.get("presets", []), key="id"
        )

    # -------- five-room orchestration --------

    def generate_five_room_dungeon(
        self,
        base_level: int,
        biome: str,
        slots: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        prog = self.tables.five_room_progression
        slot_defs = prog.get("slots") or {}

        if slots is None:
            default_order = prog.get("default_order")
            if isinstance(default_order, list) and default_order:
                slots = [str(s) for s in default_order]
            else:
                slots = list(slot_defs.keys())

        rooms: List[Dict[str, Any]] = []
        for idx, slot in enumerate(slots, start=1):
            delta_cfg = slot_defs.get(slot, {})
            delta = int(delta_cfg.get("difficulty_delta", 0))
            room_level = base_level + delta
            room_level = _clamp_level(room_level, self.tables.combat_budgets)
            encounter = self._generate_encounter_internal(
                level=room_level,
                biome=biome,
                slot=slot,
            )
            rooms.append(
                {
                    "slot": slot,
                    "room_index": idx,
                    "encounter": encounter,
                }
            )

        return {
            "schema": "dungeon.5room.v1",
            "seed": self.seed,
            "biome": biome,
            "base_level": base_level,
            "rooms": rooms,
        }

    def _generate_encounter_internal(
        self,
        level: int,
        biome: str,
        slot: str,
    ) -> Dict[str, Any]:
        enc_type = self._choose_encounter_type(slot=slot, biome=biome)
        if enc_type == "combat":
            return self._generate_combat_encounter(level=level, biome=biome, slot=slot)
        if enc_type in ("puzzle", "social", "exploration"):
            return self._generate_noncombat_encounter(
                level=level, biome=biome, slot=slot, enc_type=enc_type
            )
        return self._generate_empty_encounter(level=level, biome=biome, slot=slot)

    def generate_single_encounter(
        self,
        level: int,
        biome: str,
        slot: str,
    ) -> Dict[str, Any]:
        """Generate a single encounter with schema wrapper for standalone use."""
        encounter = self._generate_encounter_internal(level=level, biome=biome, slot=slot)
        return {
            "schema": "encounter.v1",
            "seed": self.seed,
            "encounter": encounter,
        }

    # -------- encounter type selection --------

    def _choose_encounter_type(self, slot: str, biome: str) -> str:
        data = self.tables.encounter_types
        tables = data.get("tables") or []
        if not tables:
            return "combat"

        candidates: List[Dict[str, Any]] = []
        for t in tables:
            biomes = t.get("biomes") or ["any"]
            slots = t.get("slots") or ["any"]
            biome_ok = "any" in biomes or biome in biomes
            slot_ok = "any" in slots or slot in slots
            if biome_ok and slot_ok:
                candidates.append(t)

        if not candidates:
            candidates = tables

        table = self.rng.choice(candidates)
        die = int(table.get("die", 20))
        roll = self.rng.randint(1, max(1, die))
        rows = table.get("rows") or []
        for row in rows:
            rmin = int(row.get("min", row.get("max", 1)))
            rmax = int(row.get("max", rmin))
            if rmin <= roll <= rmax:
                t = row.get("type", "combat")
                return str(t)
        return "combat"

    # -------- combat generation --------

    def _generate_combat_encounter(
        self,
        level: int,
        biome: str,
        slot: str,
    ) -> Dict[str, Any]:
        templates = self.tables.encounter_templates.get("encounter_tables") or []
        if not templates:
            raise ValueError(
                "No combat encounter templates defined in encounter_tables.json. "
                "Check that encounter_tables.json has 'encounter_tables' key with at least one entry."
            )

        candidates: List[Dict[str, Any]] = []
        for tpl in templates:
            biomes = tpl.get("biomes") or ["any"]
            slots = tpl.get("slots") or ["any"]
            min_level = int(tpl.get("min_level", 1))
            max_level = int(tpl.get("max_level", 99))
            if "any" not in biomes and biome not in biomes:
                continue
            if "any" not in slots and slot not in slots:
                continue
            if not (min_level <= level <= max_level):
                continue
            candidates.append(tpl)

        if not candidates:
            raise ValueError(
                f"No combat encounter templates match level={level}, biome={biome}, slot={slot}. "
                f"Check encounter_tables.json for templates with matching biomes/slots and level range."
            )

        weighted: List[Tuple[Dict[str, Any], float]] = []
        for tpl in candidates:
            base_weight = float(tpl.get("weight", 1.0))
            weight = base_weight * self._compute_faction_weight(tpl, slot=slot, biome=biome)
            weighted.append((tpl, weight if weight > 0 else 0.0))

        template = _weighted_choice(self.rng, weighted)

        enemy_group_id = template.get("enemy_group_id")
        enemies = self._instantiate_enemy_group(enemy_group_id, level)

        env_tags = template.get("environment_tags") or []
        env = self._select_environment(biome=biome, tags=env_tags)

        tags = list(set((template.get("tags") or []) + env.get("tags", [])))

        loot = generate_loot(
            level=level,
            rolls=int(template.get("loot_rolls", 1)),
            seed=self.rng.randint(0, 999_999),
            data_dir=self.loot_data_dir,
            data_file=self.loot_data_file,
        )

        encounter = {
            "difficulty": level,
            "type": "combat",
            "slot": slot,
            "biome": biome,
            "enemies": enemies,
            "environment": env,
            "tags": tags,
            "loot": loot,
            "meta": {
                "template_id": template.get("id"),
                "noncombat_id": None,
                "notes": template.get("notes", ""),
            },
        }
        return encounter

    def _instantiate_enemy_group(
        self,
        group_id: Optional[str],
        room_level: int,
    ) -> List[Dict[str, Any]]:
        if not group_id:
            raise ValueError("Combat template missing enemy_group_id")
        group = self._enemy_group_index.get(group_id)
        if not group:
            raise ValueError(f"Enemy group not found: {group_id}")

        out: List[Dict[str, Any]] = []
        entries = group.get("enemies") or []
        for entry in entries:
            monster_id = entry.get("monster_id")
            count_cfg = entry.get("count") or {}
            cmin = int(count_cfg.get("min", 1))
            cmax = int(count_cfg.get("max", cmin))
            if cmax < cmin:
                cmax = cmin
            count = self.rng.randint(cmin, cmax)
            if count <= 0:
                continue
            monster = self._monster_index.get(monster_id, {})
            out.append(
                {
                    "monster_id": monster_id,
                    "name": monster.get("name", monster_id),
                    "count": count,
                    "cr": monster.get("cr"),
                    "faction": monster.get("faction", group.get("faction")),
                    "tags": monster.get("tags", []),
                }
            )
        return out

    def _compute_faction_weight(
        self,
        template: Dict[str, Any],
        slot: str,
        biome: str,
    ) -> float:
        factions = template.get("factions") or []
        if not factions or not self._faction_index:
            return 1.0
        weight = 1.0
        for fid in factions:
            f = self._faction_index.get(fid)
            if not f:
                continue
            mods = f.get("weight_modifiers") or {}
            biome_mods = mods.get("biomes") or {}
            slot_mods = mods.get("slots") or {}
            if biome in biome_mods:
                try:
                    weight *= float(biome_mods[biome])
                except (TypeError, ValueError):
                    pass
            if slot in slot_mods:
                try:
                    weight *= float(slot_mods[slot])
                except (TypeError, ValueError):
                    pass
        return weight if weight > 0 else 1.0

    # -------- environment selection --------

    def _select_environment(
        self,
        biome: str,
        tags: List[str],
        specific_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        presets = self.tables.environment_presets.get("presets") or []
        if not presets:
            return {
                "preset_id": None,
                "description": "",
                "tags": [],
                "mechanical_effects": {},
            }

        if specific_id:
            env = self._env_index.get(specific_id)
            if env:
                return {
                    "preset_id": env.get("id"),
                    "description": env.get("description", ""),
                    "tags": env.get("tags", []),
                    "mechanical_effects": env.get("mechanical_effects", {}),
                }

        candidates: List[Dict[str, Any]] = []
        for env in presets:
            biomes = env.get("biomes") or ["any"]
            env_tags = env.get("tags") or []
            biome_ok = "any" in biomes or biome in biomes
            tag_match = not tags or any(t in env_tags for t in tags)
            if biome_ok and tag_match:
                candidates.append(env)

        if not candidates:
            candidates = presets

        env = self.rng.choice(candidates)
        return {
            "preset_id": env.get("id"),
            "description": env.get("description", ""),
            "tags": env.get("tags", []),
            "mechanical_effects": env.get("mechanical_effects", {}),
        }

    # -------- non-combat generation --------

    def _generate_noncombat_encounter(
        self,
        level: int,
        biome: str,
        slot: str,
        enc_type: str,
    ) -> Dict[str, Any]:
        if enc_type == "puzzle":
            table = self.tables.puzzle_tables
        elif enc_type == "social":
            table = self.tables.social_tables
        elif enc_type == "exploration":
            table = self.tables.exploration_tables
        else:
            return self._generate_empty_encounter(level, biome, slot)

        entries = table.get("entries") or []
        if not entries:
            return self._generate_empty_encounter(level, biome, slot)

        candidates: List[Dict[str, Any]] = []
        for tpl in entries:
            biomes = tpl.get("biomes") or ["any"]
            slots = tpl.get("slots") or ["any"]
            min_level = int(tpl.get("min_level", 1))
            max_level = int(tpl.get("max_level", 99))
            if "any" not in biomes and biome not in biomes:
                continue
            if "any" not in slots and slot not in slots:
                continue
            if not (min_level <= level <= max_level):
                continue
            candidates.append(tpl)

        if not candidates:
            return self._generate_empty_encounter(level, biome, slot)

        weighted: List[Tuple[Dict[str, Any], float]] = []
        for tpl in candidates:
            base_weight = float(tpl.get("weight", 1.0))
            weighted.append((tpl, base_weight))

        template = _weighted_choice(self.rng, weighted)

        env_preset_id = template.get("environment_preset_id")
        env_tags = template.get("environment_tags") or []
        env = self._select_environment(
            biome=biome, tags=env_tags, specific_id=env_preset_id
        )

        tags = list(set((template.get("tags") or []) + env.get("tags", [])))

        award_loot = bool(template.get("award_loot", False))
        loot: Optional[Dict[str, Any]]
        if award_loot:
            loot = generate_loot(
                level=level,
                rolls=int(template.get("loot_rolls", 1)),
                seed=self.rng.randint(0, 999_999),
                data_dir=self.loot_data_dir,
                data_file=self.loot_data_file,
            )
        else:
            loot = None

        encounter = {
            "difficulty": level,
            "type": enc_type,
            "slot": slot,
            "biome": biome,
            "enemies": [],
            "environment": env,
            "tags": tags,
            "loot": loot,
            "meta": {
                "template_id": None,
                "noncombat_id": template.get("id"),
                "notes": template.get("notes", ""),
            },
        }
        return encounter

    # -------- empty encounter --------

    def _generate_empty_encounter(
        self,
        level: int,
        biome: str,
        slot: str,
    ) -> Dict[str, Any]:
        return {
            "difficulty": level,
            "type": "empty",
            "slot": slot,
            "biome": biome,
            "enemies": [],
            "environment": {
                "preset_id": None,
                "description": "",
                "tags": [],
                "mechanical_effects": {},
            },
            "tags": [],
            "loot": None,
            "meta": {
                "template_id": None,
                "noncombat_id": None,
                "notes": "",
            },
        }


# --------------------------- public API --------------------------------------


def generate_five_room_dungeon(
    base_level: int,
    biome: str,
    seed: Optional[int] = None,
    data_dir: Optional[Path] = None,
    loot_data_dir: Optional[Path] = None,
    loot_data_file: str = "loot_data.json",
) -> Dict[str, Any]:
    tables = Tables.load(data_dir=data_dir)
    gen = EncounterGenerator(
        tables=tables,
        seed=seed,
        loot_data_dir=loot_data_dir,
        loot_data_file=loot_data_file,
    )
    return gen.generate_five_room_dungeon(base_level=base_level, biome=biome)


def generate_single_encounter(
    level: int,
    biome: str,
    slot: str,
    seed: Optional[int] = None,
    data_dir: Optional[Path] = None,
    loot_data_dir: Optional[Path] = None,
    loot_data_file: str = "loot_data.json",
) -> Dict[str, Any]:
    tables = Tables.load(data_dir=data_dir)
    gen = EncounterGenerator(
        tables=tables,
        seed=seed,
        loot_data_dir=loot_data_dir,
        loot_data_file=loot_data_file,
    )
    return gen.generate_single_encounter(level=level, biome=biome, slot=slot)


# --------------------------- CLI --------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate five-room dungeons or single encounters from JSON tables."
    )
    parser.add_argument(
        "--level",
        "-l",
        type=int,
        required=True,
        help="Base level / CR band for the dungeon or encounter.",
    )
    parser.add_argument(
        "--biome",
        "-b",
        type=str,
        required=True,
        help="Biome key (e.g. dungeon, forest, city).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for deterministic output.",
    )
    parser.add_argument(
        "--rooms",
        "-r",
        type=int,
        default=5,
        help="Number of rooms for five-room dungeon variant (default: 5).",
    )
    parser.add_argument(
        "--slot",
        type=str,
        default=None,
        help="Generate a single encounter for this slot (entrance/puzzle/setback/climax/aftermath). "
             "If provided, --rooms is ignored and only one encounter is generated.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Directory containing encounter JSON data files.",
    )
    parser.add_argument(
        "--loot-data-dir",
        type=Path,
        default=None,
        help="Directory containing loot_data.json (defaults to --data-dir).",
    )
    parser.add_argument(
        "--loot-data-file",
        type=str,
        default="loot_data.json",
        help="Loot data filename (default: loot_data.json).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Optional path to write JSON output (default: stdout).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    data_dir = args.data_dir
    loot_data_dir = args.loot_data_dir or data_dir

    if args.slot:
        payload = generate_single_encounter(
            level=args.level,
            biome=args.biome,
            slot=args.slot,
            seed=args.seed,
            data_dir=data_dir,
            loot_data_dir=loot_data_dir,
            loot_data_file=args.loot_data_file,
        )
    else:
        payload = generate_five_room_dungeon(
            base_level=args.level,
            biome=args.biome,
            seed=args.seed,
            data_dir=data_dir,
            loot_data_dir=loot_data_dir,
            loot_data_file=args.loot_data_file,
        )

    text = json.dumps(payload, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
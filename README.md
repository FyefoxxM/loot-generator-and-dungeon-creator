# Encounter & Loot Generator

A library-first, JSON-driven encounter and loot generation system for fantasy RPGs. Build procedurally generated five-room dungeons with weighted enemy placement, faction-based encounters, and integrated loot drops.

## Features

- **Deterministic Generation**: Seed-based randomization for reproducible encounters and loot
- **Library-First Design**: Import as Python modules or use standalone CLI tools
- **JSON-Driven Data**: All content in human-editable JSON files - no code changes needed
- **Standardized Schemas**: Consistent output formats (`loot.v1`, `encounter.v1`, `dungeon.5room.v1`)
- **Faction System**: 10 factions with biome/slot weight modifiers for intelligent enemy placement
- **Level Scaling**: Full support for levels 1-20 with appropriate difficulty curves
- **Rich Encounter Types**: Combat, puzzle, social, exploration, and empty encounters
- **Biome Coverage**: 9 distinct biomes with faction preferences and environmental effects

## Installation

```bash
git clone https://github.com/yourusername/encountergen.git
cd encountergen
```

No external dependencies required - uses Python 3.10+ standard library only.

## Quick Start

### Command Line

Generate a five-room dungeon:
```bash
python encountergen.py --level 5 --biome temperate_forest --seed 1234 \
    --data-dir data --loot-data-dir data --output dungeon.json
```

Generate loot:
```bash
python lootgen.py --level 5 --rolls 2 --seed 1234 \
    --data-dir data --output loot.json
```

### Library Usage

```python
from pathlib import Path
from encountergen import generate_five_room_dungeon
from lootgen import generate_loot

# Generate a complete dungeon
dungeon = generate_five_room_dungeon(
    base_level=5,
    biome="temperate_forest",
    seed=1234,
    data_dir=Path("data"),
    loot_data_dir=Path("data")
)

# Generate loot separately
loot = generate_loot(
    level=5,
    rolls=2,
    seed=1234,
    data_dir=Path("data")
)
```

## Project Structure

```
encountergen/
├── encountergen.py              # Five-room dungeon generator
├── lootgen.py                   # Loot generation system
├── data/                        # JSON configuration files
│   ├── loot_data.json          # Loot tables and budgets
│   ├── monsters.json           # Monster definitions (50+ creatures)
│   ├── factions.json           # Faction weight modifiers
│   ├── enemy_groups.json       # Pre-composed enemy groups
│   ├── encounter_tables.json   # Combat encounter templates
│   ├── encounter_types.json    # Encounter type distributions
│   ├── five_room_progression.json  # Dungeon slot configuration
│   ├── combat_budgets.json     # Level-based difficulty budgets
│   ├── puzzle_tables.json      # Puzzle encounter templates
│   ├── social_tables.json      # Social encounter templates
│   └── exploration_tables.json # Exploration encounter templates
├── examples/                    # Example outputs
├── tests/                       # Unit and integration tests
└── README.md
```

## JSON Schemas

### Five-Room Dungeon Output (`dungeon.5room.v1`)

```json
{
  "schema": "dungeon.5room.v1",
  "seed": 1234,
  "biome": "temperate_forest",
  "base_level": 5,
  "rooms": [
    {
      "slot": "entrance",
      "room_index": 1,
      "encounter": {
        "difficulty": 5,
        "type": "combat",
        "slot": "entrance",
        "biome": "temperate_forest",
        "enemies": [
          {
            "monster_id": "goblin",
            "name": "Goblin",
            "count": 4,
            "cr": 0.25,
            "faction": "goblin_clan",
            "tags": ["humanoid", "sneaky"]
          }
        ],
        "environment": {...},
        "tags": ["ambush", "raiders"],
        "loot": {...},
        "meta": {...}
      }
    }
  ]
}
```

### Loot Output (`loot.v1`)

```json
{
  "schema": "loot.v1",
  "seed": 1234,
  "encounter_level": 5,
  "rolls": 2,
  "parcels": [
    {
      "coins": {
        "pp": 7,
        "gp": 3,
        "sp": 46,
        "cp": 143
      },
      "magic_items": [
        {
          "id": "potion_healing",
          "name": "Potion of Healing",
          "rarity": "common",
          "gp_value": 50.0
        }
      ],
      "mundane_items": [...],
      "total_value_gp": 104.03
    }
  ]
}
```

## Supported Biomes

- `temperate_forest` - Forests with goblins, beasts, and bandits
- `grassland` - Open plains with orcs and bandits
- `wetlands` - Swamps with bog coven and undead
- `desert` - Arid lands with desert reavers and undead
- `highland` - Rocky terrain with orcs and stone legion
- `mountain` - Peaks with stone legion and mountain hunters
- `ocean` - Coastal waters with drowned cult
- `deep_ocean` - Deep seas with tidespawn
- `beach` - Shorelines with cult activity

## Encounter Slots

Five-room dungeons follow this progression:

1. **Entrance** (difficulty +0) - Guardian or initial challenge
2. **Puzzle** (difficulty +0) - Problem-solving or trap room
3. **Setback** (difficulty +1) - Mid-dungeon complication
4. **Climax** (difficulty +2) - Boss fight or major challenge
5. **Aftermath** (difficulty -1) - Cooldown or treasure room

## Extending the System

### Adding New Monsters

Edit `data/monsters.json`:

```json
{
  "id": "your_monster",
  "name": "Your Monster",
  "cr": 2,
  "faction": "your_faction",
  "tags": ["beast", "flying"]
}
```

### Adding New Encounters

Edit `data/encounter_tables.json`:

```json
{
  "id": "your_encounter",
  "biomes": ["temperate_forest"],
  "slots": ["entrance", "setback"],
  "min_level": 1,
  "max_level": 10,
  "weight": 1.2,
  "enemy_group_id": "your_enemy_group",
  "factions": ["your_faction"],
  "tags": ["ambush"],
  "environment_tags": ["cover"],
  "loot_rolls": 1
}
```

### Adding Custom Loot

Edit `data/loot_data.json`:

```json
{
  "magic_items": [
    {
      "id": "your_item",
      "name": "Your Magic Item",
      "rarity": "uncommon",
      "min_level": 3,
      "max_level": 20,
      "gp_value": 250,
      "weight": 2
    }
  ]
}
```

## Design Principles

This project follows "Week 2" architecture patterns:

1. **Seed Everything**: All randomization uses deterministic seeds
2. **Standardized JSON**: Consistent output schemas with version tags
3. **Human-Editable Data**: All content in flat JSON files
4. **Library-First**: CLI is a thin wrapper around importable functions

## CLI Reference

### encountergen.py

```bash
python encountergen.py [OPTIONS]

Options:
  --level, -l INT        Base level/CR (required)
  --biome, -b STRING     Biome name (required)
  --seed INT             Random seed for deterministic output
  --slot STRING          Generate single encounter for this slot
  --data-dir PATH        Directory containing encounter JSON files
  --loot-data-dir PATH   Directory containing loot_data.json
  --output, -o PATH      Output file (default: stdout)
```

### lootgen.py

```bash
python lootgen.py [OPTIONS]

Options:
  --level, -l INT        Encounter level/CR (required)
  --rolls, -r INT        Number of loot parcels (default: 1)
  --seed INT             Random seed for deterministic output
  --data-dir PATH        Directory containing loot_data.json
  --output, -o PATH      Output file (default: stdout)
```

## Testing

Run local tests:

```bash
python test_local.py
```

Or test individual components:

```python
from pathlib import Path
from lootgen import generate_loot

loot = generate_loot(level=5, rolls=1, seed=42, data_dir=Path("data"))
assert loot["schema"] == "loot.v1"
assert len(loot["parcels"]) == 1
print("✓ Loot generation works")
```


## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all existing tests pass
5. Submit a pull request

## Acknowledgments

Built as part of the "30 for 30" coding challenge - 30 developer tools in 30 days.

#!/usr/bin/env python3
"""
lootgen.py

Library-first loot generator for fantasy RPG encounters.
Compatible with loot_data.json schema with id, weight, level gating.

Library API:
    from pathlib import Path
    from lootgen import generate_loot

    loot_payload = generate_loot(
        level=5,
        rolls=2,
        seed=1234,
        data_dir=Path("data"),
        data_file="loot_data.json"
    )

CLI:
    python lootgen.py --level 7 --rolls 2 --seed 1001 --data-dir data --output loot.json
"""

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_loot_data(data_dir: Optional[Path] = None, filename: str = "loot_data.json") -> Dict[str, Any]:
    """Load and validate loot data JSON."""
    if data_dir is None:
        data_dir = Path(__file__).parent
    data_dir = Path(data_dir)
    
    path = data_dir / filename
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: {filename} not found in {data_dir}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing {filename}: {e}", file=sys.stderr)
        sys.exit(1)

    required_keys = ["coin_values_gp", "level_budgets_gp", "magic_items", "mundane_goods"]
    for k in required_keys:
        if k not in data:
            raise ValueError(f"loot_data.json missing required key: {k}")

    return data


# ---------------------------------------------------------------------------
# Filtering and selection
# ---------------------------------------------------------------------------

def _filter_magic_by_level(items: List[Dict[str, Any]], level: int) -> List[Dict[str, Any]]:
    """Filter magic items by min_level and max_level gates."""
    out = []
    for it in items:
        lo = int(it.get("min_level", 1))
        hi = int(it.get("max_level", 20))
        if lo <= level <= hi:
            out.append(it)
    return out


def _weighted_choice(rng: random.Random, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Select item from list using weight field."""
    if not items:
        return {}
    weights = [float(it.get("weight", 1.0)) for it in items]
    return rng.choices(items, weights=weights, k=1)[0]


# ---------------------------------------------------------------------------
# Coin generation
# ---------------------------------------------------------------------------

def _generate_coins(
    rng: random.Random,
    coin_values: Dict[str, float],
    budget_gp: float
) -> Dict[str, int]:
    """
    Convert GP budget into random mixture of coins.
    Prefers higher denominations but includes randomness.
    """
    coins_sorted = sorted(coin_values.items(), key=lambda x: -x[1])
    
    remaining = budget_gp
    output = {}
    
    for coin, value in coins_sorted:
        if remaining <= 0:
            break
        max_qty = int(remaining / value)
        if max_qty <= 0:
            continue
        qty = rng.randint(0, max_qty)
        if qty > 0:
            output[coin] = qty
            remaining -= qty * value
    
    return output


def _calculate_parcel_value(
    parcel: Dict[str, Any],
    coin_values: Dict[str, float]
) -> float:
    """Calculate total GP value of a loot parcel."""
    total = 0.0
    
    # Coins
    coins = parcel.get("coins", {})
    for denom, count in coins.items():
        value = coin_values.get(denom, 0.0)
        total += value * int(count)
    
    # Magic items
    for item in parcel.get("magic_items", []):
        total += float(item.get("gp_value", 0.0))
    
    # Mundane items
    for item in parcel.get("mundane_items", []):
        total += float(item.get("gp_value", 0.0))
    
    return total


# ---------------------------------------------------------------------------
# Core generator
# ---------------------------------------------------------------------------

class LootGenerator:
    """Core loot generator with deterministic seed support."""
    
    def __init__(self, loot_data: Dict[str, Any], seed: Optional[int] = None):
        self.loot_data = loot_data
        self.seed = seed if seed is not None else random.randint(0, 999_999)
        self.rng = random.Random(self.seed)
        
        self.coin_values = loot_data["coin_values_gp"]
        self.level_budgets = loot_data["level_budgets_gp"]
        self.magic_items = loot_data["magic_items"]
        self.mundane_goods = loot_data["mundane_goods"]
    
    def generate(self, level: int, rolls: int = 1) -> Dict[str, Any]:
        """Generate loot parcels for given level."""
        rolls = max(1, int(rolls))
        
        # Validate level
        if str(level) not in self.level_budgets:
            raise ValueError(f"Level {level} not found in level_budgets_gp")
        
        base_budget = float(self.level_budgets[str(level)])
        magic_pool = _filter_magic_by_level(self.magic_items, level)
        
        parcels: List[Dict[str, Any]] = []
        
        for _ in range(rolls):
            parcel = self._generate_parcel(level, base_budget, magic_pool)
            parcels.append(parcel)
        
        return {
            "schema": "loot.v1",
            "seed": self.seed,
            "encounter_level": level,
            "rolls": rolls,
            "parcels": parcels,
        }
    
    def _generate_parcel(
        self,
        level: int,
        base_budget: float,
        magic_pool: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate a single loot parcel."""
        parcel: Dict[str, Any] = {
            "coins": {},
            "magic_items": [],
            "mundane_items": []
        }
        
        # 1) Generate coins (20% of budget)
        coin_budget = base_budget * 0.20
        coins = _generate_coins(self.rng, self.coin_values, coin_budget)
        parcel["coins"] = coins
        
        # 2) Roll for magic vs mundane item (40% magic, 60% mundane)
        if self.rng.random() < 0.4 and magic_pool:
            item = _weighted_choice(self.rng, magic_pool)
            parcel["magic_items"].append({
                "id": item["id"],
                "name": item["name"],
                "rarity": item.get("rarity", "common"),
                "gp_value": float(item["gp_value"])
            })
        else:
            item = _weighted_choice(self.rng, self.mundane_goods)
            parcel["mundane_items"].append({
                "id": item["id"],
                "name": item["name"],
                "gp_value": float(item["gp_value"])
            })
        
        # Calculate total value
        parcel["total_value_gp"] = round(
            _calculate_parcel_value(parcel, self.coin_values),
            2
        )
        
        return parcel


# ---------------------------------------------------------------------------
# Public API (library entry point)
# ---------------------------------------------------------------------------

def generate_loot(
    level: int,
    rolls: int = 1,
    seed: Optional[int] = None,
    data_dir: Optional[Path] = None,
    data_file: str = "loot_data.json",
) -> Dict[str, Any]:
    """
    Generate loot parcels based on encounter level.
    
    Args:
        level: Encounter level / challenge rating
        rolls: Number of loot parcels to generate
        seed: Random seed for deterministic output
        data_dir: Directory containing loot_data.json
        data_file: Loot data filename
    
    Returns:
        Dict with schema "loot.v1" containing parcels
    """
    loot_data = _load_loot_data(data_dir=data_dir, filename=data_file)
    gen = LootGenerator(loot_data, seed=seed)
    return gen.generate(level=level, rolls=rolls)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate loot parcels based on encounter level (loot.v1)."
    )
    parser.add_argument(
        "--level",
        "-l",
        type=int,
        required=True,
        help="Encounter level / challenge rating.",
    )
    parser.add_argument(
        "--rolls",
        "-r",
        type=int,
        default=1,
        help="Number of loot parcels to generate (default: 1).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for deterministic output.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Directory containing loot_data.json (default: script directory).",
    )
    parser.add_argument(
        "--data-file",
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
    payload = generate_loot(
        level=args.level,
        rolls=args.rolls,
        seed=args.seed,
        data_dir=args.data_dir,
        data_file=args.data_file,
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
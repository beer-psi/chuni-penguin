from pathlib import Path
from typing import Literal

import platformdirs

# Threshold for matching song titles.
SIMILARITY_THRESHOLD = 65

# Chart constant of the hardest song in the game.
# Probably not the best way to implement this but whatever.
MAX_DIFFICULTY = 15.7

ChunithmVersion = Literal[
    "CHUNITHM",
    "CHUNITHM PLUS",
    "AIR",
    "AIR PLUS",
    "STAR",
    "STAR PLUS",
    "AMAZON",
    "AMAZON PLUS",
    "CRYSTAL",
    "CRYSTAL PLUS",
    "PARADISE",
    "PARADISE LOST",
    "NEW",
    "NEW PLUS",
    "SUN",
    "SUN PLUS",
    "LUMINOUS",
    "LUMINOUS PLUS",
    "VERSE",
    "X-VERSE",
    "X-VERSE-X",
]
# Used to split old records from new records.
CURRENT_CHUNITHM_VERSION = "X-VERSE"

# The version names are just my favorite CHUNITHM songs
# in no particular order.
VERSION_NAMES = {
    "v0.2.1": "Ray of Hope",
    "v0.2.2": "parvorbital",
    "v0.2.3": "Spider's Thread",
    "v2024.12": "Shattered Memories",
    "v2025.1": "Cries, beyond The End",
    "v2025.3": "[CRYSTAL_ACCESS]",
    "v2025.4": "Oracle",
    "v2025.5": "黎命に殉ず",
    "v2025.6": "deadeye",
    "v2025.9": "Elusive Enforcer",
    "v2025.11": "Parallel Horizons",
    "v2026.1": "Dèfandour",
}

ASSETS_DIR = Path(__file__).parent.parent / "assets"
CACHE_DIR = Path(platformdirs.user_cache_dir("chuni-penguin", "beerpsi"))

from math import ceil


def calculate_teampoint(score: int, internal_level: float) -> int:
    return int(ceil((internal_level * 5 + 100) * (score ** 3) * 1e-18) + 10)

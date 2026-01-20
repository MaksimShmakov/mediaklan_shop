from typing import Optional


def parse_optional_int(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    return int(value)


def parse_variants_raw(raw: str) -> list[dict]:
    variants = []
    if not raw:
        return variants
    normalized = raw.replace(";", "|")
    for line in normalized.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        parts = [part.strip() for part in cleaned.split("|") if part.strip()]
        if len(parts) < 2:
            continue
        label = parts[0]
        try:
            points_cost = int(parts[1])
        except ValueError:
            continue
        stock = None
        if len(parts) >= 3:
            try:
                stock = parse_optional_int(parts[2])
            except ValueError:
                stock = None
        variants.append(
            {
                "label": label,
                "points_cost": points_cost,
                "stock": stock,
                "position": len(variants),
            }
        )
    return variants

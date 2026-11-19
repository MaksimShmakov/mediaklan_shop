import re

from typing import Optional

from app.services.auth import normalize_tg_username

SEPARATORS = ("\t", ";", ",", "|")


def _split_line(line: str) -> list[str]:
    cleaned = line.strip()
    for separator in SEPARATORS:
        cleaned = cleaned.replace(separator, " ")
    return [part for part in cleaned.split(" ") if part]


def parse_bulk_users(raw: str) -> tuple[list[dict], list[str]]:
    """Разбирает строки вида "@user 500" в список пользователей.

    Баллы можно не указывать — тогда points будет None и текущее
    значение пользователя останется прежним.
    """
    parsed: list[dict] = []
    errors: list[str] = []
    seen: set[str] = set()

    for line in (raw or "").splitlines():
        if not line.strip():
            continue
        parts = _split_line(line)
        if not parts:
            continue

        username = normalize_tg_username(parts[0])
        if not username:
            errors.append(line.strip())
            continue

        points: Optional[int] = None
        if len(parts) > 1:
            points_raw = parts[1].replace(" ", "")
            try:
                points = int(points_raw)
            except ValueError:
                errors.append(line.strip())
                continue
            if points < 0:
                errors.append(line.strip())
                continue

        if username in seen:
            continue
        seen.add(username)
        parsed.append({"tg_username": username, "points": points})

    return parsed, errors


def parse_delete_usernames(raw: str) -> list[str]:
    """Validate the entire list before any destructive operation."""
    if len(raw) > 65536:
        raise ValueError("Список слишком большой (максимум 1000 ников).")
    tokens = [token for token in re.split(r"[\s,;|]+", raw.strip()) if token]
    if not tokens:
        raise ValueError("Введите хотя бы один Telegram-ник.")
    if any(not re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{0,31}", token) for token in tokens):
        raise ValueError("Вставьте только Telegram-ники, без баллов и ссылок. Ничего не удалено.")
    usernames = list(dict.fromkeys(normalize_tg_username(token) for token in tokens))
    if len(usernames) > 1000:
        raise ValueError("За один раз можно удалить не более 1000 ников.")
    return usernames

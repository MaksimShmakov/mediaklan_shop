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


def split_delete_entries(raw: str) -> list[str]:
    """Spaces can belong to legacy names: never split a name on a space."""
    if len(raw) > 65536:
        raise ValueError("Список слишком большой (максимум 1000 ников).")
    entries = list(dict.fromkeys(
        entry.strip() for entry in re.split(r"[\r\n\t,;|]+", raw) if entry.strip()
    ))
    if not entries:
        raise ValueError("Введите хотя бы один Telegram-ник.")
    if len(entries) > 1000:
        raise ValueError("За один раз можно удалить не более 1000 ников.")
    return entries


def parse_delete_usernames(raw: str, existing_usernames: set[str] | None = None) -> list[str]:
    """Accept exact legacy DB names without guessing or repairing their spelling."""
    existing = existing_usernames or set()
    usernames = []
    for entry in split_delete_entries(raw):
        username = normalize_tg_username(entry)
        if username not in existing and not re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_.]{0,31}", entry):
            raise ValueError(
                f"Не удалось распознать запись «{entry[:80]}». "
                "Укажите один ник на строку без баллов и ссылок. "
                "Ники с пробелами должны точно совпадать с записью в базе. Ничего не удалено."
            )
        usernames.append(username)
    return list(dict.fromkeys(usernames))

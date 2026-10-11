"""Разбор номеров из запросов панели — в одном месте (внешний аудит 09.10.2026, A10).

str.isdigit() пропускает «²» и «①», которые int() не понимает, и сколь угодно длинные числа —
отсюда были ответы 500. Здесь — только цифры 0–9 и разумная длина; иначе «нет такого номера».
"""

import re

_ID = re.compile(r'[0-9]{1,12}')


def to_id(raw):
    """Номер записи или None."""
    raw = str(raw if raw is not None else '').strip()
    return int(raw) if _ID.fullmatch(raw) else None


def to_ids(values):
    """Список номеров; None, если хоть один кривой."""
    ids = [to_id(v) for v in values]
    return None if any(i is None for i in ids) else ids

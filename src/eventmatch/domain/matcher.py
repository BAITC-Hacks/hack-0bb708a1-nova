"""Deterministic catalog matching. No network or model credentials required."""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path


class CatalogError(ValueError):
    pass


def normalized(value: str) -> str:
    return " ".join(value.casefold().replace("ё", "е").split())


def tokens(value: str) -> Counter:
    return Counter(re.findall(r"[а-яa-z0-9]+", normalized(value)))


def sequence(value, field: str) -> list[str]:
    # The supplied CSV uses pipes, including for multivalued categories.
    if isinstance(value, str):
        if value.lstrip().startswith("["):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise CatalogError(f"{field}: некорректный массив JSON.") from exc
        else:
            value = value.split("|") if value.strip() else []
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise CatalogError(f"{field}: ожидается список непустых строк.")
    return [x.strip() for x in value]


def number(value, field: str, nullable=False):
    if nullable and (value is None or value == "" or value == "null"):
        return None
    if isinstance(value, bool) or value is None:
        raise CatalogError(f"{field}: ожидается неотрицательное число.")
    try:
        parsed = float(value)
    except (ValueError, TypeError) as exc:
        raise CatalogError(f"{field}: ожидается число без символа валюты.") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise CatalogError(f"{field}: ожидается конечное неотрицательное число.")
    return parsed


def flag(value, field: str) -> bool:
    if value is True or value is False:
        return value
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    raise CatalogError(f"{field}: ожидается true или false.")


def iso_date(value: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Дата должна иметь формат ГГГГ-ММ-ДД.")
    return date.fromisoformat(value)


@dataclass(frozen=True)
class Contractor:
    id: str
    anon_name: str
    categories: tuple[str, ...]
    city: str
    price_from_kzt: float
    event_formats: tuple[str, ...]
    languages: tuple[str, ...]
    max_hours: float | None
    busy_dates: tuple[str, ...]
    description: str
    synthetic: bool
    city_imputed: bool
    price_imputed: bool


def load_catalog(path: str | Path) -> list[Contractor]:
    """Read UTF-8(-BOM) JSON arrays or CSV with pipe-separated list cells.

    Fail closed: missing constraints must never silently broaden eligibility.
    """
    path = Path(path)
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            if path.suffix.lower() == ".csv":
                rows = list(csv.DictReader(handle))
            elif path.suffix.lower() == ".json":
                rows = json.load(handle)
            else:
                raise CatalogError("Поддерживаются файлы .json и .csv.")
    except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
        raise CatalogError(f"Не удалось прочитать каталог: {exc}") from exc
    if not isinstance(rows, list) or not rows:
        raise CatalogError("Каталог должен содержать непустой список профилей.")
    result, ids = [], set()
    required = set(Contractor.__dataclass_fields__)
    for index, row in enumerate(rows, 1):
        try:
            if not isinstance(row, dict):
                raise CatalogError("профиль должен быть объектом.")
            missing = required - row.keys()
            if missing:
                raise CatalogError(f"отсутствуют поля: {', '.join(sorted(missing))}.")
            if isinstance(row["id"], bool) or not isinstance(row["id"], (str, int)):
                raise CatalogError("id должен быть строкой или целым числом.")
            data = {key: row[key] for key in required}
            data["id"] = str(row["id"]).strip()
            if not data["id"] or data["id"] in ids:
                raise CatalogError("пустой или повторяющийся id.")
            for key in ("anon_name", "city", "description"):
                if not isinstance(data[key], str) or not data[key].strip():
                    raise CatalogError(f"{key}: ожидается непустая строка.")
                data[key] = data[key].strip()
            for key in ("categories", "event_formats", "languages", "busy_dates"):
                data[key] = tuple(sequence(data[key], key))
            if not data["categories"] or not data["event_formats"]:
                raise CatalogError("categories и event_formats не могут быть пустыми.")
            for busy in data["busy_dates"]:
                iso_date(busy)
            data["price_from_kzt"] = number(data["price_from_kzt"], "price_from_kzt")
            data["max_hours"] = number(data["max_hours"], "max_hours", nullable=True)
            for key in ("synthetic", "city_imputed", "price_imputed"):
                data[key] = flag(data[key], key)
            result.append(Contractor(**data))
            ids.add(data["id"])
        except (ValueError, TypeError) as exc:
            raise CatalogError(f"Профиль {index}: {exc}") from exc
    return result


@dataclass(frozen=True)
class Request:
    city: str
    event_date: str
    event_type: str
    category: str
    budget_kzt: float
    duration_hours: float | None = None
    language: str | None = None

    def __post_init__(self):
        iso_date(self.event_date)
        for key in ("city", "event_type", "category"):
            if not isinstance(getattr(self, key), str) or not getattr(self, key).strip():
                raise ValueError(f"Поле {key} обязательно.")
        if isinstance(self.budget_kzt, bool) or not isinstance(self.budget_kzt, (int, float)) or not math.isfinite(self.budget_kzt) or self.budget_kzt <= 0:
            raise ValueError("Бюджет должен быть положительным числом.")
        if self.duration_hours is not None and (isinstance(self.duration_hours, bool) or not isinstance(self.duration_hours, (int, float)) or not math.isfinite(self.duration_hours) or self.duration_hours <= 0):
            raise ValueError("Продолжительность должна быть положительным числом.")
        if self.language is not None and (not isinstance(self.language, str) or not self.language.strip()):
            raise ValueError("Язык должен быть непустой строкой.")


def contains(values, requested: str) -> bool:
    return normalized(requested) in {normalized(v) for v in values}


REASONS = {
    "busy": "заняты в выбранную дату",
    "event_format": "не поддерживают формат мероприятия",
    "budget": "начальная цена выше бюджета",
    "duration": "доступная продолжительность меньше запрошенной",
}


def filter_candidates(catalog: list[Contractor], request: Request):
    scoped = [c for c in catalog if normalized(c.city) == normalized(request.city) and contains(c.categories, request.category)]
    survivors, rejected = [], Counter()
    for c in scoped:
        reasons = []
        if request.event_date in c.busy_dates:
            reasons.append("busy")
        if not contains(c.event_formats, request.event_type):
            reasons.append("event_format")
        if c.price_from_kzt > request.budget_kzt:
            reasons.append("budget")
        if request.duration_hours is not None and c.max_hours is not None and c.max_hours < request.duration_hours:
            reasons.append("duration")
        if reasons:
            rejected.update(reasons)
        else:
            survivors.append(c)
    return scoped, survivors, rejected


def semantic_scores(catalog: list[Contractor], request: Request) -> dict[str, float]:
    """Local TF-IDF cosine; corpus is the full catalog, including rejected rows."""
    docs = {c.id: tokens(c.description) for c in catalog}
    frequency = Counter(word for doc in docs.values() for word in doc)
    idf = {word: math.log((1 + len(docs)) / (1 + count)) + 1 for word, count in frequency.items()}

    def vector(counts):
        return {word: count * idf[word] for word, count in sorted(counts.items()) if word in idf}

    query = vector(tokens(f"{request.category} {request.event_type} {request.language or ''}"))
    query_norm = math.sqrt(sum(x * x for x in query.values()))
    result = {}
    for cid, doc in docs.items():
        vec = vector(doc)
        denominator = query_norm * math.sqrt(sum(x * x for x in vec.values()))
        result[cid] = sum(value * vec.get(word, 0) for word, value in query.items()) / denominator if denominator else 0.0
    return result


def rank_candidates(candidates: list[Contractor], catalog: list[Contractor], request: Request):
    semantics = semantic_scores(catalog, request)
    ranked = []
    for c in candidates:
        # Budget proximity is a modest preference, never an inferred quality claim.
        budget = 15 * max(0, 1 - abs(c.price_from_kzt / request.budget_kzt - 0.75) / 0.75)
        language = 30 * (contains(c.languages, request.language) if request.language else 1)
        if request.duration_hours is None or c.max_hours is None:
            duration = 15.0
        else:
            duration = 10 + 5 * min((c.max_hours - request.duration_hours) / request.duration_hours, 1)
        parts = {"Формат": 20.0, "Бюджет": budget, "Язык": float(language), "Продолжительность": duration, "Описание": 20 * semantics[c.id]}
        score = sum(parts.values())
        ranked.append((c, score, parts))
    return sorted(ranked, key=lambda item: (-item[1], item[0].id))


def money(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ") + " ₸"


def explain(c: Contractor, request: Request) -> str:
    day = iso_date(request.event_date).strftime("%d.%m.%Y")
    facts = [f"«{c.anon_name}» ({request.category}, {c.city}) свободен по календарю на {day}",
             f"поддерживает формат «{request.event_type}»", f"цена от {money(c.price_from_kzt)} при бюджете {money(request.budget_kzt)}"]
    if request.duration_hours is not None:
        facts.append("ограничение по часам неприменимо" if c.max_hours is None else f"лимит {c.max_hours:g} ч покрывает ваши {request.duration_hours:g} ч")
    if request.language:
        facts.append(f"язык «{request.language}» указан" if contains(c.languages, request.language) else f"язык «{request.language}» не указан в профиле")
    # Exact excerpt: never paraphrase profile text into an unsupported promise.
    excerpt = re.split(r"(?<=[.!?])\s+", c.description.strip())[0]
    if len(excerpt) > 200:
        excerpt = excerpt[:197].rsplit(" ", 1)[0] + "…"
    return "; ".join(facts) + f". Из описания: «{excerpt}»"


def recommend(catalog: list[Contractor], request: Request) -> dict:
    scoped, survivors, rejected = filter_candidates(catalog, request)
    common = {"cards": [], "rejections": dict(rejected), "city_category_count": len(scoped), "eligible_count": len(survivors)}
    if not scoped:
        return {**common, "status": "CATEGORY_NOT_FOUND", "message": f"В городе «{request.city}» нет подрядчиков категории «{request.category}»."}
    if not survivors:
        details = "; ".join(f"{rejected[key]} — {label}" for key, label in REASONS.items() if rejected[key])
        return {**common, "status": "NO_MATCH", "message": f"Никто не соответствует условиям: {details}. У одного профиля может быть несколько причин отказа."}
    cards = []
    for c, score, parts in rank_candidates(survivors, catalog, request)[:3]:
        cards.append({"contractor": c, "score": round(score, 3), "score_parts": {k: round(v, 3) for k, v in parts.items()}, "explanation": explain(c, request)})
    message = f"Найдено подходящих подрядчиков: {len(survivors)}. Показаны лучшие {len(cards)}."
    if len(survivors) < 3:
        message += " Менее трёх профилей соответствуют всем обязательным условиям."
    return {**common, "status": "SUCCESS", "message": message, "cards": cards}

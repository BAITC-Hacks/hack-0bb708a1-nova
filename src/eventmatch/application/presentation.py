"""User-facing wording only; matcher outcomes and rejection counts stay intact."""
import re

from eventmatch.domain.matcher import REASONS, Request, contains, iso_date, money


def result_message(result, request):
    if result["status"] == "CATEGORY_NOT_FOUND":
        return f"В этой локации пока нет подрядчиков категории «{request.category}»."
    if result["status"] == "NO_MATCH":
        reasons = [f"{result['rejections'][key]} — "
                   + (f"заняты {readable_date(request.event_date)}" if key == "busy" else label)
                   for key, label in REASONS.items()
                   if result["rejections"].get(key)]
        return ("Подходящих вариантов не нашлось.\n\nВ выбранной категории есть подрядчики, но:\n\n"
                + "\n".join(reasons)
                + "\n\nУ одного подрядчика может быть несколько причин несовпадения.")
    count = len(result["cards"])
    if result["eligible_count"] < 3:
        return "Под ваши условия подходит один вариант." if count == 1 else "Под ваши условия подходят два варианта."
    return "Вот три варианта, которые подходят под ваши условия."


MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря")


def readable_date(value, include_year=False):
    day = iso_date(value)
    text = f"{day.day} {MONTHS[day.month - 1]}"
    return f"{text} {day.year}" if include_year else text


def summary(request: Request) -> str:
    parts = [request.city, readable_date(request.event_date, include_year=True),
             f"{request.event_type.capitalize()} · {request.category}", f"До {money(request.budget_kzt)}"]
    optional = []
    if request.duration_hours is not None:
        optional.append(f"{request.duration_hours:g} ч")
    if request.language:
        optional.append(request.language)
    if optional:
        parts.append(" · ".join(optional))
    return "\n".join(parts)


def confirmation_text(request):
    return "Проверьте условия\n\n" + summary(request)


def card_explanation(contractor, request):
    """Concise factual fallback for selected cards; never mutates matcher output."""
    first = (f"По календарю свободен {readable_date(request.event_date)}; "
             f"начальная цена от {money(contractor.price_from_kzt)} укладывается в бюджет.")
    if request.language and not contains(contractor.languages, request.language):
        return first + f" Язык «{request.language}» в профиле не указан."
    # Exact, bounded profile excerpt rather than an invented description.
    excerpt = re.split(r"(?<=[.!?])\s+", contractor.description.strip())[0]
    if len(excerpt) > 160:
        excerpt = excerpt[:157].rsplit(" ", 1)[0] + "…"
    return first + f" Из профиля: «{excerpt}»"


def outcome_text(result, request):
    text = result_message(result, request)
    if result["status"] == "NO_MATCH":
        suggestions = []
        for key, suggestion in (("busy", "другую дату"), ("budget", "другой бюджет"),
                                ("duration", "меньшую продолжительность"), ("event_format", "другой формат")):
            if result["rejections"].get(key):
                suggestions.append(suggestion)
        text += "\n\nМожно проверить " + " или ".join(suggestions[:2]) + "."
    elif result["status"] == "CATEGORY_NOT_FOUND":
        text += "\n\nМожно проверить другую категорию или локацию."

    return text

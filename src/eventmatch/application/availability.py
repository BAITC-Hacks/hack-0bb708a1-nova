"""Product calendar coverage, validated before calling the unchanged matcher."""
from datetime import date

from eventmatch.domain.matcher import iso_date

FIRST_DATE = date(2026, 9, 23)
LAST_DATE = date(2026, 12, 31)
WINDOW_LABEL = "23.09.2026–31.12.2026"
WINDOW_MESSAGE = (
    f"Данные о доступности подрядчиков есть только за {WINDOW_LABEL}. "
    "Какую дату в этом диапазоне выберем?"
)


class DateOutsideWindow(ValueError):
    pass


def validate_event_date(value: str | date) -> date:
    parsed = iso_date(value) if isinstance(value, str) else value
    if not isinstance(parsed, date):
        raise ValueError("Выберите дату мероприятия.")
    if not FIRST_DATE <= parsed <= LAST_DATE:
        raise DateOutsideWindow(WINDOW_MESSAGE)
    return parsed

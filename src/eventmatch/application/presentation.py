"""User-facing wording only; matcher outcomes and rejection counts stay intact."""
from eventmatch.domain.matcher import REASONS, Request, iso_date, money


def result_message(result, request):
    if result["status"] == "CATEGORY_NOT_FOUND":
        return f"В этой локации пока нет подрядчиков категории «{request.category}»."
    if result["status"] == "NO_MATCH":
        reasons = [f"{result['rejections'][key]} — {label}" for key, label in REASONS.items()
                   if result["rejections"].get(key)]
        return ("Подрядчики этой категории есть, но сейчас никто не подходит под все условия.\n\n"
                + "\n".join(reasons)
                + "\n\nУ одного подрядчика может быть несколько причин несовпадения.")
    count = len(result["cards"])
    if result["eligible_count"] < 3:
        return f"Под ваши условия подходит меньше трёх подрядчиков — показываю все варианты ({count})."
    return "Вот три варианта, которые подходят под ваши условия."


def summary(request: Request) -> str:
    parts = [f"Локация: {request.city}", f"Дата: {iso_date(request.event_date).strftime('%d.%m.%Y')}",
             f"Мероприятие: {request.event_type}", f"Категория: {request.category}",
             f"Бюджет: до {money(request.budget_kzt)}"]
    if request.duration_hours is not None:
        parts.append(f"Продолжительность: {request.duration_hours:g} ч")
    if request.language:
        parts.append(f"Предпочитаемый язык: {request.language}")
    return "\n".join(parts)


def confirmation_text(request):
    return "Проверим, правильно ли я поняла:\n\n" + summary(request) + "\n\nВсё верно — искать по этим условиям? Можно подтвердить или поправить детали."


def outcome_text(result, request):
    text = result_message(result, request)
    if result["status"] == "NO_MATCH":
        suggestions = []
        for key, suggestion in (("busy", "другую дату"), ("budget", "другой бюджет"),
                                ("duration", "меньшую продолжительность"), ("event_format", "другой формат")):
            if result["rejections"].get(key):
                suggestions.append(suggestion)
        text += " Если ваши планы позволяют, можем проверить " + ", ".join(suggestions) + ". Что хотите изменить?"
    elif result["status"] == "CATEGORY_NOT_FOUND":
        text += " Можем проверить другую категорию или локацию — что вам подходит?"
    else:
        text += " Можно уточнить бюджет, дату или другие условия — я сделаю новый подбор."
    return text

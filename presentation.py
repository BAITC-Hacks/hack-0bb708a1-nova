"""User-facing wording only; matcher outcomes and rejection counts stay intact."""
from matcher import REASONS


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

"""Original manual form and demos, retained alongside chat."""
from datetime import date

import streamlit as st

from demo import DEMOS
from matcher import Request, money, recommend


def render_manual(catalog):
    def apply_demo():
        request = DEMOS[st.session_state.demo_choice]
        st.session_state.update(
            city=request.city, event_date=date.fromisoformat(request.event_date),
            event_type=request.event_type, category=request.category,
            budget=int(request.budget_kzt), duration=float(request.duration_hours or 0),
            language=request.language or "Не важно",
        )


    st.selectbox("Сценарий для демонстрации", list(DEMOS), key="demo_choice", on_change=apply_demo)
    if "city" not in st.session_state:
        apply_demo()

    # Keep widgets outside a form so changing inputs immediately removes stale results.
    left, right = st.columns(2)
    with left:
        city = st.selectbox("Город", sorted({c.city for c in catalog}), key="city")
        event_type = st.selectbox("Тип мероприятия", sorted({f for c in catalog for f in c.event_formats}), key="event_type")
        budget = st.number_input("Бюджет, ₸", min_value=1, step=50_000, key="budget")
    with right:
        event_date = st.date_input("Дата мероприятия", key="event_date", format="DD.MM.YYYY")
        category = st.selectbox("Категория подрядчика", sorted({v for c in catalog for v in c.categories}), key="category")
        duration = st.number_input("Продолжительность, ч (0 — не указана)", min_value=0.0, step=0.5, key="duration")
    language = st.selectbox("Предпочитаемый язык", ["Не важно"] + sorted({v for c in catalog for v in c.languages}), key="language")
    st.caption("Язык влияет на порядок результатов. Если он не указан в профиле, это отмечено в объяснении.")
    st.caption("Подбор учитывает начальную цену из каталога; итоговая стоимость в данных не указана.")

    if st.button("Найти подрядчиков", type="primary", use_container_width=True):
        try:
            request = Request(city, event_date.isoformat(), event_type, category, budget, duration or None,
                              None if language == "Не важно" else language)
            result = recommend(catalog, request)
        except ValueError as exc:
            st.error(str(exc))
            st.stop()

        if result["status"] == "CATEGORY_NOT_FOUND":
            st.warning("Категория отсутствует в городе")
            st.write(result["message"])
        elif result["status"] == "NO_MATCH":
            st.warning("Нет подходящих подрядчиков")
            st.write(result["message"])
        else:
            st.success(result["message"])
            for index, card in enumerate(result["cards"], 1):
                c = card["contractor"]
                with st.container(border=True):
                    st.subheader(f"{index}. {c.anon_name}")
                    st.write(f"{category} · {c.city} · от {money(c.price_from_kzt)}")
                    st.caption("Синтетический профиль" if c.synthetic else "Исходный профиль")
                    labels = []
                    if c.city_imputed:
                        labels.append("Город восстановлен в датасете")
                    if c.price_imputed:
                        labels.append("Цена восстановлена в датасете")
                    if labels:
                        st.caption(" · ".join(labels))
                    st.write(card["explanation"])
                    hours = "Ограничение по часам неприменимо" if c.max_hours is None else f"До {c.max_hours:g} ч"
                    st.caption(f"Языки: {', '.join(c.languages) or 'не указаны'} · {hours}")
                    st.caption("Форматы: " + ", ".join(c.event_formats))
                    with st.expander("Почему такой порядок результатов"):
                        st.write(f"Оценка соответствия: {card['score']:.3f} из 100")
                        st.table([{"Критерий": key, "Баллы": value} for key, value in card["score_parts"].items()])

    with st.expander("Как работает подбор"):
        st.write("Сначала проверяем город, категорию, занятость, формат, бюджет и продолжительность. "
                 "Затем сравниваем язык, соответствие бюджету, запас времени и слова из описания.")
        st.write("Совпадение языка даёт до 30 баллов, описание — до 20, бюджет — до 15, "
                 "продолжительность — до 15; поддерживаемый формат даёт 20 баллов. "
                 "При равенстве оценок порядок определяется идентификатором профиля.")
        st.caption("Свободная дата означает отсутствие даты в списке занятости каталога. "
                   "Список занятости в предоставленных данных охватывает сентябрь–декабрь 2026 года.")

"""Original manual form and demos, retained alongside chat."""
from datetime import date

import streamlit as st

from demo import DEMOS
from matcher import Request, recommend
from availability_window import DateOutsideWindow, FIRST_DATE, LAST_DATE, WINDOW_LABEL, WINDOW_MESSAGE, validate_event_date
from presentation import result_message
from ui_components import prose, render_cards


def render_manual(catalog):
    def apply_demo():
        request = DEMOS[st.session_state.demo_choice]
        st.session_state.update(
            city=request.city, event_date=date.fromisoformat(request.event_date),
            event_type=request.event_type, category=request.category,
            budget=int(request.budget_kzt), duration=float(request.duration_hours or 0),
            language=request.language or "Не важно",
        )


    with st.expander("Демо-сценарии"):
        st.selectbox("Выберите сценарий", list(DEMOS), key="demo_choice", on_change=apply_demo)
    if "city" not in st.session_state:
        apply_demo()
    if st.session_state.get("event_date") is not None:
        try:
            validate_event_date(st.session_state.event_date)
        except DateOutsideWindow:
            # A pre-polish browser session may contain an unsupported date.
            # Ask for a new choice rather than silently clamping the old date.
            st.session_state.event_date = None
            st.info(WINDOW_MESSAGE)

    # Keep widgets outside a form so changing inputs immediately removes stale results.
    left, right = st.columns(2)
    with left:
        city = st.selectbox("Локация", sorted({c.city for c in catalog}), key="city")
        event_type = st.selectbox("Тип мероприятия", sorted({f for c in catalog for f in c.event_formats}), key="event_type")
        budget = st.number_input("Бюджет, ₸", min_value=1, step=50_000, key="budget")
    with right:
        event_date = st.date_input("Дата мероприятия", key="event_date", format="DD.MM.YYYY",
                                   min_value=FIRST_DATE, max_value=LAST_DATE,
                                   help=f"Доступность известна только за {WINDOW_LABEL}.")
        category = st.selectbox("Категория подрядчика", sorted({v for c in catalog for v in c.categories}), key="category")
        duration = st.number_input("Продолжительность, ч (0 — не указана)", min_value=0.0, step=0.5, key="duration")
    language = st.selectbox("Предпочитаемый язык", ["Не важно"] + sorted({v for c in catalog for v in c.languages}), key="language")
    st.caption("Язык влияет на порядок результатов. Если он не указан в профиле, это отмечено в объяснении.")
    st.caption("Подбор учитывает начальную цену из каталога; итоговая стоимость в данных не указана.")

    if st.button("Найти подрядчиков", type="primary", use_container_width=True):
        try:
            validate_event_date(event_date)
            request = Request(city, event_date.isoformat(), event_type, category, budget, duration or None,
                              None if language == "Не важно" else language)
            result = recommend(catalog, request)
        except ValueError as exc:
            st.error(str(exc))
            st.stop()

        if result["status"] == "SUCCESS":
            st.success(result_message(result, request))
            render_cards(result, request)
        else:
            st.warning("Нет подходящих вариантов" if result["status"] == "NO_MATCH" else "Категория пока недоступна")
            prose(result_message(result, request))

    with st.expander("Как работает подбор"):
        st.write("Сначала проверяем город, категорию, занятость, формат, бюджет и продолжительность. "
                 "Затем сравниваем язык, соответствие бюджету, запас времени и слова из описания.")
        st.write("Совпадение языка даёт до 30 баллов, описание — до 20, бюджет — до 15, "
                 "продолжительность — до 15; поддерживаемый формат даёт 20 баллов. "
                 "При равенстве оценок порядок определяется идентификатором профиля.")
        st.caption("Свободная дата означает отсутствие даты в списке занятости каталога. "
                   "Список занятости в предоставленных данных охватывает сентябрь–декабрь 2026 года.")

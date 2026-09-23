"""Original manual form and demos, retained alongside chat."""
import streamlit as st

from eventmatch.ui.demo_scenarios import DEMOS
from eventmatch.domain.matcher import Request, recommend
from eventmatch.application.availability import FIRST_DATE, LAST_DATE, WINDOW_LABEL, validate_event_date
from eventmatch.application.presentation import outcome_text
from eventmatch.ui.components import prose, render_cards
from eventmatch.ui.state import apply_demo, initialize_manual


def render_manual(catalog, review=False):
    if review:
        with st.expander("Примеры поиска"):
            st.selectbox("Выберите пример", list(DEMOS), key="demo_choice",
                         on_change=apply_demo, args=(st.session_state,))
    if notice := initialize_manual(st.session_state):
        st.info(notice)

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
        duration = st.number_input("Продолжительность, ч", min_value=0.0, step=0.5, key="duration", help="Необязательно. Оставьте 0, если длительность пока неизвестна.")
    language = st.selectbox("Предпочитаемый язык", ["Не важно"] + sorted({v for c in catalog for v in c.languages}), key="language")
    st.caption("Язык и продолжительность можно не указывать.")

    if st.button("Найти подрядчиков", type="primary", key="search_manual"):
        try:
            validate_event_date(event_date)
            request = Request(city, event_date.isoformat(), event_type, category, budget, duration or None,
                              None if language == "Не важно" else language)
            result = recommend(catalog, request)
        except ValueError as exc:
            st.error(str(exc))
            st.stop()

        prose(outcome_text(result, request))
        render_cards(result, request, review=review)

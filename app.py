"""Streamlit entry point. Chat state belongs only to the current browser session."""
import streamlit as st

from conversation import Conversation, confirm_search, handle_message, summary
from demo import CATALOG_PATH
from llm_client import AgentError, OpenAIBackend, configuration
from manual_ui import render_manual
from matcher import CatalogError, load_catalog, money


def render_chat_cards(message):
    result, request = message.result, message.request
    if result["status"] == "NO_MATCH":
        st.warning("Нет подходящих подрядчиков")
    elif result["status"] == "CATEGORY_NOT_FOUND":
        st.warning("Категория отсутствует в городе")
    with st.expander("Условия этого поиска"):
        st.text(summary(request))
    for index, card in enumerate(result["cards"], 1):
        c = card["contractor"]
        with st.container(border=True):
            st.subheader(f"{index}. {c.anon_name}")
            st.text(f"{request.category} · {c.city} · от {money(c.price_from_kzt)}")
            st.caption("Синтетический профиль" if c.synthetic else "Исходный профиль")
            labels = []
            if c.city_imputed:
                labels.append("Город восстановлен в датасете")
            if c.price_imputed:
                labels.append("Цена восстановлена в датасете")
            if labels:
                st.caption(" · ".join(labels))
            st.text(card["explanation"])
            hours = "Ограничение по часам неприменимо" if c.max_hours is None else f"До {c.max_hours:g} ч"
            st.caption(f"Языки: {', '.join(c.languages) or 'не указаны'} · {hours}")
            st.caption("Форматы: " + ", ".join(c.event_formats))
            with st.expander("Почему такой порядок результатов"):
                st.write(f"Оценка соответствия: {card['score']:.3f} из 100")
                st.table([{"Критерий": k, "Баллы": v} for k, v in card["score_parts"].items()])
    if result["cards"] and message.explanation_source != "ai":
        st.caption("Для части карточек использовано объяснение напрямую из фактов каталога.")


def render_chat(catalog):
    if "conversation" not in st.session_state:
        st.session_state.conversation = Conversation()
    state = st.session_state.conversation
    configured = bool(configuration()[0])
    st.write("Опишите задачу своими словами. Я уточню детали и попрошу подтвердить условия перед поиском.")
    st.caption("Например: «Нужен ведущий на свадьбу в Алматы 2 ноября 2026, до 2 млн тенге, на 6 часов, на русском».")
    if not configured:
        st.info("Для чата нужно добавить OPENAI_API_KEY в .env. Подбор во вкладке «Форма и демо» работает без ключа.")
    st.caption("Бюджет — на одного подрядчика. Цены в каталоге начальные; язык — предпочтение при ранжировании.")
    if st.button("Новый разговор", key="reset_chat"):
        st.session_state.conversation = Conversation()
        st.rerun()

    for message in state.messages:
        with st.chat_message(message.role):
            st.text(message.text)
            if message.result is not None:
                render_chat_cards(message)

    if state.pending is not None:
        if st.button("Подтвердить и найти", key="confirm_chat", type="primary"):
            with st.spinner("Проверяю каталог и готовлю объяснения…"):
                try:
                    backend = OpenAIBackend()
                    state.add("user", "Подтверждаю условия, найти подрядчиков.")
                    confirm_search(state, catalog, backend)
                except AgentError as exc:
                    state.add("assistant", str(exc))
            st.rerun()

    if text := st.chat_input("Расскажите о мероприятии или уточните условия…", max_chars=4000, key="chat_message"):
        with st.spinner("Разбираю ваше сообщение…"):
            try:
                handle_message(state, text, catalog, OpenAIBackend())
            except AgentError as exc:
                state.add("assistant", str(exc))
        st.rerun()


st.set_page_config(page_title="Nova · Подбор подрядчиков", page_icon="✨", layout="centered")
st.title("Nova · Подбор подрядчиков")
st.write("Ваш координатор мероприятий в Казахстане — от идеи до трёх подходящих подрядчиков.")
try:
    catalog = load_catalog(CATALOG_PATH)
except CatalogError as exc:
    st.error(str(exc))
    st.stop()
st.caption(f"В каталоге: {len(catalog)} профилей · Из них синтетических: {sum(c.synthetic for c in catalog)}")
form_tab, chat_tab = st.tabs(["Форма и демо", "Разговор с Nova"], default="Разговор с Nova")
# Chat opens by default; the manual form retains its original widget order.
with form_tab:
    render_manual(catalog)
with chat_tab:
    render_chat(catalog)

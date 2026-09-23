"""Streamlit entry point. Chat state belongs only to the current browser session."""
import streamlit as st

from conversation import Conversation, confirm_search, handle_message, summary
from demo import CATALOG_PATH
from llm_client import AgentError, OpenAIBackend, configuration
from manual_ui import render_manual
from matcher import CatalogError, load_catalog
from ui_components import prose, render_cards


def render_chat_cards(message):
    result, request = message.result, message.request
    if result["status"] == "NO_MATCH":
        st.warning("Нет подходящих подрядчиков")
    elif result["status"] == "CATEGORY_NOT_FOUND":
        st.warning("Категория пока недоступна")
    with st.expander("Условия этого поиска"):
        prose(summary(request))
    render_cards(result, request)


def render_chat(catalog):
    if "conversation" not in st.session_state:
        st.session_state.conversation = Conversation()
    state = st.session_state.conversation
    configured = bool(configuration()[0])
    if not configured:
        st.info("Чат пока недоступен. Вы можете найти подрядчиков во вкладке «Поиск по параметрам».")
    if len(state.messages) > 1 and st.button("Новый разговор", key="reset_chat"):
        st.session_state.conversation = Conversation()
        st.rerun()

    for message in state.messages:
        with st.chat_message(message.role):
            prose(message.text)
            if message is state.messages[0] and len(state.messages) == 1:
                st.caption("Например: «Ищу ведущего на свадьбу в Алматы 14 ноября 2026, бюджет до 800 000 ₸».")
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


st.set_page_config(page_title="EventMatch", page_icon="✨", layout="centered")
st.title("EventMatch")
st.write("Умный подбор подрядчиков для вашего мероприятия")
st.caption("Расскажите о мероприятии — я уточню детали и предложу до трёх подходящих вариантов.")
try:
    catalog = load_catalog(CATALOG_PATH)
except CatalogError as exc:
    st.error(str(exc))
    st.stop()
form_tab, chat_tab = st.tabs(["Поиск по параметрам", "Подбор в чате"], default="Подбор в чате")
# Chat opens by default; the manual form retains its original widget order.
with form_tab:
    render_manual(catalog)
with chat_tab:
    render_chat(catalog)

with st.expander("О сервисе"):
    st.write("Подбираем до трёх вариантов по локации, дате, формату мероприятия и бюджету. Цены начальные; итоговую стоимость нужно уточнять у подрядчика.")
    st.write("Данные о доступности: 23.09.2026–31.12.2026. Свободная дата означает, что в календаре каталога нет отметки о занятости.")
    st.caption(f"В каталоге {len(catalog)} профилей, в том числе {sum(c.synthetic for c in catalog)} синтетических — они отмечены на карточках.")

"""Chat widgets and rendering; orchestration lives in conversation.py."""
import streamlit as st

from eventmatch.ai.models import AgentError
from eventmatch.application.conversation import confirm_search, handle_message
from eventmatch.application.presentation import summary
from eventmatch.ui.components import prose, render_cards
from eventmatch.ui.state import get_conversation, new_conversation


def render_chat_cards(message):
    result, request = message.result, message.request
    if result["status"] == "NO_MATCH":
        st.warning("Нет подходящих подрядчиков")
    elif result["status"] == "CATEGORY_NOT_FOUND":
        st.warning("Категория пока недоступна")
    with st.expander("Условия этого поиска"):
        prose(summary(request))
    # Older in-memory messages already carry their displayed text in result.
    render_cards(result, request, explanations=getattr(message, "explanations", {}))


def render_chat(catalog, backend_factory, configured):
    state = get_conversation(st.session_state)
    if not configured:
        st.info("Чат пока недоступен. Вы можете найти подрядчиков во вкладке «Поиск по параметрам».")
    if len(state.messages) > 1 and st.button("Новый разговор", key="reset_chat"):
        new_conversation(st.session_state)
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
                    backend = backend_factory()
                    state.add("user", "Подтверждаю условия, найти подрядчиков.")
                    confirm_search(state, catalog, backend)
                except AgentError as exc:
                    state.add("assistant", str(exc))
            st.rerun()

    if text := st.chat_input("Расскажите о мероприятии или уточните условия…", max_chars=4000, key="chat_message"):
        with st.spinner("Разбираю ваше сообщение…"):
            try:
                handle_message(state, text, catalog, backend_factory())
            except AgentError as exc:
                state.add("assistant", str(exc))
        st.rerun()

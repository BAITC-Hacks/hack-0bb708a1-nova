"""Chat widgets and rendering; orchestration lives in conversation.py."""
import streamlit as st

from eventmatch.ai.models import AgentError
from eventmatch.application.conversation import INTRO, confirm_search, handle_message
from eventmatch.application.presentation import summary
from eventmatch.ui.components import prose, render_cards
from eventmatch.ui.state import get_conversation


def render_chat_cards(message, review=False):
    result, request = message.result, message.request
    if review:
        with st.expander("Условия этого поиска"):
            prose(summary(request))
    # Older in-memory messages already carry their displayed text in result.
    render_cards(result, request, explanations=getattr(message, "explanations", {}), review=review)


def render_chat(catalog, backend_factory, configured, review=False):
    state = get_conversation(st.session_state)
    if not configured:
        st.caption("Чат пока недоступен. Попробуйте позже.")
    initial = len(state.messages) == 1
    if initial:
        st.markdown("**Опишите мероприятие и кого вы ищете.**")

    for index, message in enumerate(state.messages):
        if initial:
            break
        if index == 0 and message.role == "assistant" and message.text == INTRO:
            continue
        with st.chat_message(message.role):
            # Old provider errors can still refer to the removed form. Adapt only
            # their visible wording; the stored conversation and backend stay intact.
            text = message.text
            if message.role == "assistant" and "«Поиск по параметрам»" in text:
                text = "Чат временно недоступен. Ваши условия сохранены; попробуйте отправить сообщение позже."
            if message.role == "assistant" and text.startswith("Проверьте условия\n\n"):
                st.markdown("**Проверьте условия**")
                prose(text.split("\n\n", 1)[1])
            else:
                prose(text)
            if message.result is not None:
                render_chat_cards(message, review=review)

    if state.pending is not None:
        if st.button("Найти подрядчиков", key="confirm_chat", type="primary"):
            with st.spinner("Подбираю варианты…"):
                try:
                    backend = backend_factory()
                    state.add("user", "Подтверждаю условия, найти подрядчиков.")
                    confirm_search(state, catalog, backend)
                except AgentError as exc:
                    state.add("assistant", str(exc))
            st.rerun()

    placeholder = "Введите сообщение…" if initial else "Что уточним или изменим?"
    if text := st.chat_input(placeholder, max_chars=4000, key="chat_message"):
        with st.spinner("Уточняю детали…"):
            try:
                handle_message(state, text, catalog, backend_factory())
            except AgentError as exc:
                state.add("assistant", str(exc))
        st.rerun()

    if initial:
        st.caption("Например: «Нужен ведущий на свадьбу в Алматы 14 ноября 2026, бюджет до 800 000 ₸».")

"""Small shared Streamlit components for chat and parameter search."""
import re

import streamlit as st

from eventmatch.application.presentation import card_explanation
from eventmatch.domain.matcher import money
from eventmatch.ui.state import get_conversation, new_conversation


def apply_style():
    # Native theming handles color/type/borders. Streamlit has no avatar-off option;
    # keep accessible chat roles and hide only their decorative avatar elements.
    st.html("""<style>
        [data-testid="stChatMessageAvatarAssistant"],
        [data-testid="stChatMessageAvatarUser"] { display: none; }
        [data-testid="stMainBlockContainer"] {
            max-width: 48rem; padding-top: 2.5rem; padding-bottom: 2rem;
        }
        .st-key-product_header { margin-bottom: 1.75rem; }
        [data-testid="stChatMessage"] { border-radius: 0; padding: 0.75rem 0; }
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
            margin-left: auto; width: fit-content; max-width: 88%;
            border-radius: 0.625rem; padding: 0.75rem 1rem;
        }
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p {
            line-height: 1.65;
        }
        .st-key-product_information { margin-top: 1.5rem; }
        @media (max-width: 480px) {
            [data-testid="stMainBlockContainer"] { padding-top: 1.25rem; }
            .st-key-product_header { margin-bottom: 1rem; }
            [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
                max-width: 94%;
            }
        }
    </style>""")


def prose(text):
    # Use normal typography without interpreting user/model Markdown as links/images.
    escaped = re.sub(r"([\\`*_{}\[\]()#+\-.!|>~])", r"\\\1", text)
    st.markdown(escaped.replace("\n", "  \n"))


def render_reset():
    state = get_conversation(st.session_state)
    st.button("Новый поиск", key="reset_chat", on_click=new_conversation,
              args=(st.session_state,), disabled=len(state.messages) == 1,
              type="tertiary", wrap=False)


def render_information():
    with st.expander("О сервисе"):
        st.write("Подбор до трёх подрядчиков по условиям вашего мероприятия. "
                 "Указаны начальные цены; итоговую стоимость и бронирование нужно уточнять у подрядчика.")
        st.caption("Доступность: 23.09.2026–31.12.2026. "
                   "Свободная дата означает отсутствие отметки о занятости в календаре.")
    with st.expander("Как работает подбор"):
        st.write("Сначала проверяем обязательные условия: локацию, категорию, дату, формат, бюджет "
                 "и длительность, если она указана. Затем сравниваем подходящие варианты, "
                 "учитывая в том числе предпочтения по языку.")
        st.write("AI помогает понять запрос и вести диалог, но не определяет доступность "
                 "или соответствие обязательным условиям.")


def render_cards(result, request, explanations=None, review=False):
    explanations = explanations or {}
    for card in result["cards"]:
        c = card["contractor"]
        st.divider()
        with st.container(horizontal=True, vertical_alignment="top", gap="medium"):
            with st.container(gap="xxsmall"):
                st.subheader(c.anon_name, anchor=False)
                st.caption(f"{request.category} · {c.city}")
            with st.container(width="content"):
                st.markdown(f"**от {money(c.price_from_kzt)}**")
        prose(explanations.get(c.id) or card_explanation(c, request))
        # Null means not applicable, never unlimited working time.
        hours = "Учёт часов не требуется" if c.max_hours is None else f"До {c.max_hours:g} ч"
        with st.container(gap="xxsmall"):
            st.caption(f"Языки: {', '.join(c.languages) or 'не указаны'} · {hours}")
            st.caption(f"Форматы: {', '.join(c.event_formats)}")
        labels = []
        if c.synthetic:
            labels.append("Синтетический профиль")
        if c.price_imputed:
            labels.append("Ориентировочная цена")
        if c.city_imputed:
            labels.append("Локация указана ориентировочно")
        if labels:
            st.caption(" · ".join(labels))
    if review and result["cards"]:
        with st.expander("Подробности подбора"):
            for card in result["cards"]:
                prose(card["contractor"].anon_name)
                st.caption(f"Соответствие условиям: {card['score']:.1f} из 100")
                st.table([{"Критерий": k, "Баллы": round(v, 1)} for k, v in card["score_parts"].items()])

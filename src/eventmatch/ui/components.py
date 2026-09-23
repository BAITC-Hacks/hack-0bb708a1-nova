"""Small shared Streamlit components for chat and parameter search."""
import re

import streamlit as st

from eventmatch.domain.matcher import money


def prose(text):
    # Use normal typography without interpreting user/model Markdown as links/images.
    escaped = re.sub(r"([\\`*_{}\[\]()#+\-.!|>~])", r"\\\1", text)
    st.markdown(escaped.replace("\n", "  \n"))


def render_cards(result, request, explanations=None):
    explanations = explanations or {}
    for card in result["cards"]:
        c = card["contractor"]
        with st.container(border=True):
            st.subheader(c.anon_name)
            st.caption(f"{request.category} · {c.city}")
            st.markdown(f"**от {money(c.price_from_kzt)}**")
            labels = []
            if c.synthetic:
                labels.append("Синтетический профиль")
            if c.price_imputed:
                labels.append("Ориентировочная цена")
            if c.city_imputed:
                labels.append("Локация указана ориентировочно")
            if labels:
                st.caption(" · ".join(labels))
            # Preserve verified LLM explanations; remove only a redundant prefix
            # from deterministic fallback text, without changing any facts.
            explanation = explanations.get(c.id, card["explanation"])
            prefix = f"«{c.anon_name}» ({request.category}, {c.city})"
            if explanation.startswith(prefix):
                explanation = c.anon_name + explanation[len(prefix):]
            prose(explanation)
            # Null means not applicable, not unlimited working time.
            hours = "Учёт часов не требуется для этой услуги" if c.max_hours is None else f"До {c.max_hours:g} ч"
            st.caption(f"Языки: {', '.join(c.languages) or 'не указаны'} · {hours}")
            st.caption("Форматы: " + ", ".join(c.event_formats))
            with st.expander("Как подобран этот вариант"):
                st.write(f"Оценка соответствия: {card['score']:.3f} из 100")
                st.table([{"Критерий": k, "Баллы": v} for k, v in card["score_parts"].items()])

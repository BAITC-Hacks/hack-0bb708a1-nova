"""Streamlit entry point. Chat state belongs only to the current browser session."""
import streamlit as st

from eventmatch.ui.chat import render_chat
from eventmatch.paths import CATALOG_PATH
from eventmatch.infrastructure.openai_client import OpenAIBackend, configuration
from eventmatch.ui.components import apply_style, render_reset, render_information
from eventmatch.domain.matcher import CatalogError, load_catalog


st.set_page_config(page_title="EventMatch", layout="centered")
apply_style()
review = st.query_params.get("review") == "1"
with st.container(key="product_header", horizontal=True, vertical_alignment="center", gap="medium"):
    with st.container(gap="xxsmall"):
        st.title("EventMatch")
        st.caption("Подрядчики для вашего мероприятия")
    with st.container(width="content"):
        render_reset()
try:
    catalog = load_catalog(CATALOG_PATH)
except CatalogError:
    st.error("Не удалось загрузить список подрядчиков. Попробуйте открыть сервис позже.")
    st.stop()
# Nesting keeps chat_input inline, above the information at the end of the page.
with st.container():
    render_chat(catalog, OpenAIBackend, configured=bool(configuration()[0]), review=review)

with st.container(key="product_information", gap="xsmall"):
    render_information()

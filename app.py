"""Streamlit entry point. Chat state belongs only to the current browser session."""
import streamlit as st

from eventmatch.ui.chat import render_chat
from eventmatch.paths import CATALOG_PATH
from eventmatch.infrastructure.openai_client import OpenAIBackend, configuration
from eventmatch.ui.manual import render_manual
from eventmatch.domain.matcher import CatalogError, load_catalog


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
    render_chat(catalog, OpenAIBackend, configured=bool(configuration()[0]))

with st.expander("О сервисе"):
    st.write("Подбираем до трёх вариантов по локации, дате, формату мероприятия и бюджету. Цены начальные; итоговую стоимость нужно уточнять у подрядчика.")
    st.write("Данные о доступности: 23.09.2026–31.12.2026. Свободная дата означает, что в календаре каталога нет отметки о занятости.")
    st.caption(f"В каталоге {len(catalog)} профилей, в том числе {sum(c.synthetic for c in catalog)} синтетических — они отмечены на карточках.")

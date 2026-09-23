"""UI session lifecycle helpers. Accept a mapping; never import Streamlit.

Widgets still own their keyed values. Only initialization, demo loading and
conversation replacement are centralized here; domain code knows no session keys.
"""
from datetime import date

from eventmatch.application.availability import DateOutsideWindow, WINDOW_MESSAGE, validate_event_date
from eventmatch.application.conversation import Conversation
from eventmatch.ui.demo_scenarios import DEMOS


def get_conversation(session):
    if "conversation" not in session:
        new_conversation(session)
    return session["conversation"]


def new_conversation(session):
    session["conversation"] = Conversation()


def apply_demo(session):
    request = DEMOS[session["demo_choice"]]
    session.update(
        city=request.city, event_date=date.fromisoformat(request.event_date),
        event_type=request.event_type, category=request.category,
        budget=int(request.budget_kzt), duration=float(request.duration_hours or 0),
        language=request.language or "Не важно",
    )


def initialize_manual(session):
    if "city" not in session:
        apply_demo(session)
    if session.get("event_date") is not None:
        try:
            validate_event_date(session["event_date"])
        except DateOutsideWindow:
            # Preserve the existing migration behavior: clear, never clamp.
            session["event_date"] = None
            return WINDOW_MESSAGE
    return None

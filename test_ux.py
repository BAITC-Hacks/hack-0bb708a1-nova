"""Product date-window safety and UX smoke tests. No API calls required."""
import unittest
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from agent_models import Ambiguity, Update
from availability_window import DateOutsideWindow, FIRST_DATE, LAST_DATE, WINDOW_MESSAGE, validate_event_date
from conversation import Conversation, confirm_search, handle_message
from demo import DEMOS
from llm_client import AgentError
from matcher import recommend
from presentation import result_message
from test_conversation import decision
from test_matcher import BASE, QUERY


class DateWindowTests(unittest.TestCase):
    def test_inclusive_boundaries(self):
        for day in (FIRST_DATE, LAST_DATE):
            self.assertEqual(validate_event_date(day.isoformat()), day)
            request = replace(QUERY, event_date=day.isoformat())
            state = Conversation(draft=asdict(request), pending=request)
            backend = Mock()
            backend.explain.return_value = {}
            with patch("conversation.recommend", wraps=recommend) as matcher:
                confirm_search(state, [BASE], backend)
                matcher.assert_called_once_with([BASE], request)

    def test_outside_boundaries(self):
        for day in ("2026-09-22", "2027-01-01", "2025-11-14", "2030-11-14"):
            with self.assertRaisesRegex(DateOutsideWindow, "23.09.2026–31.12.2026"):
                validate_event_date(day)

    def test_missing_date_rejected(self):
        with self.assertRaises(ValueError):
            validate_event_date(None)

    def test_chat_new_or_corrected_date_blocks_search_then_recovers(self):
        for known in (False, True):
            for day in ("2026-09-22", "2027-01-01"):
                with self.subTest(known=known, day=day):
                    state = Conversation(draft=asdict(QUERY), pending=QUERY) if known else Conversation()
                    backend = Mock()
                    backend.parse.return_value = decision(updates=[Update(field="event_date", value=day, evidence=day)],
                                                         ambiguities=[Ambiguity(field="event_date", question="Какая дата?")])
                    with patch("conversation.recommend") as matcher:
                        handle_message(state, day, [BASE], backend)
                        self.assertIsNone(state.pending)
                        self.assertEqual(state.messages[-1].text, WINDOW_MESSAGE)
                        self.assertEqual(state.unresolved["event_date"], WINDOW_MESSAGE)
                        confirm_search(state, [BASE], backend)
                        matcher.assert_not_called()
                    corrected = "2026-12-31"
                    backend.parse.return_value = decision(updates=[Update(field="event_date", value=corrected, evidence=corrected)])
                    handle_message(state, corrected, [BASE], backend)
                    self.assertNotIn("event_date", state.unresolved)
                    self.assertEqual(state.draft["event_date"], corrected)
                    if known:
                        self.assertEqual(state.pending.event_date, corrected)
                        self.assertEqual(state.pending.budget_kzt, QUERY.budget_kzt)

    def test_stale_confirmation_cannot_bypass_window(self):
        request = replace(QUERY, event_date="2027-01-01")
        state = Conversation(draft=asdict(request), pending=request)
        backend = Mock()
        with patch("conversation.recommend") as matcher:
            handle_message(state, "да", [BASE], backend)
            matcher.assert_not_called()
        self.assertEqual(state.messages[-1].text, WINDOW_MESSAGE)
        self.assertIsNone(state.pending)
        backend.explain.assert_not_called()

    def test_stale_draft_cannot_create_pending_outside_window(self):
        request = replace(QUERY, event_date="2027-01-01")
        state = Conversation(draft=asdict(request))
        backend = Mock()
        backend.parse.return_value = decision()
        handle_message(state, "Повтори поиск", [BASE], backend)
        self.assertIsNone(state.pending)
        self.assertEqual(state.messages[-1].text, WINDOW_MESSAGE)


class PolishUITests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=20).run()

    def test_branding_labels_collapsed_details_and_date_picker(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "EventMatch")
        self.assertEqual([t.label for t in app.tabs], ["Поиск по параметрам", "Подбор в чате"])
        self.assertEqual(app.selectbox(key="city").label, "Локация")
        demos = next(e for e in app.expander if e.label == "Демо-сценарии")
        self.assertFalse(demos.proto.expanded)
        self.assertTrue(any(e.label == "О сервисе" and not e.proto.expanded for e in app.expander))
        date_widget = app.date_input(key="event_date")
        self.assertEqual(date_widget.min, FIRST_DATE)
        self.assertEqual(date_widget.max, LAST_DATE)

    def test_old_manual_date_does_not_silently_clamp_or_search(self):
        # Seed a pre-polish session; the restricted date picker itself refuses
        # out-of-range widget updates before they can reach the application.
        app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=20)
        for key, value in {"city": "Алматы", "event_date": date(2027, 1, 1),
                           "event_type": "свадьба", "category": "Ведущий", "budget": 2000000,
                           "duration": 6.0, "language": "русский"}.items():
            app.session_state[key] = value
        app.run()
        self.assertFalse(app.exception)
        self.assertIsNone(app.date_input(key="event_date").value)
        self.assertTrue(any(WINDOW_MESSAGE in x.value for x in app.info))
        with patch("manual_ui.recommend") as matcher:
            app.button[0].click().run()
            matcher.assert_not_called()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)

    def test_synthetic_estimated_labels_and_score_expander(self):
        app = self.app()
        app.selectbox(key="demo_choice").select(list(DEMOS)[1]).run()
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.subheader), 1)
        captions = " ".join(c.value for c in app.caption)
        self.assertIn("Синтетический профиль", captions)
        self.assertNotIn("Исходный профиль", captions)
        self.assertNotIn("восстановлена в датасете", captions)
        self.assertTrue(any(e.label == "Как подобран этот вариант" and not e.proto.expanded for e in app.expander))

    def test_chat_api_failure_keeps_manual_fallback_working(self):
        backend = Mock()
        backend.parse.side_effect = AgentError("Чат временно недоступен. Используйте «Поиск по параметрам».")
        with patch("llm_client.OpenAIBackend", return_value=backend):
            app = self.app()
            app.chat_input[0].set_value("Нужен ведущий").run()
            self.assertFalse(app.exception)
            self.assertIsNone(app.session_state.conversation.pending)
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.subheader), 3)

    def test_no_match_presentation_retains_every_rejection_count(self):
        request = replace(QUERY, budget_kzt=1)
        result = recommend([replace(BASE, busy_dates=(QUERY.event_date,))], request)
        before = result.copy()
        text = result_message(result, request)
        self.assertIn("никто не подходит под все условия", text)
        self.assertIn("1 — заняты", text)
        self.assertIn("1 — начальная цена выше бюджета", text)
        self.assertEqual(result, before)


if __name__ == "__main__":
    unittest.main()

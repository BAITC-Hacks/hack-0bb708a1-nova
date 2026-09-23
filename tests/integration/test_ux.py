"""Product date-window safety and UX smoke tests. No API calls required."""
import unittest
from dataclasses import replace
from datetime import date
from tests.support import ROOT
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from eventmatch.application.availability import FIRST_DATE, LAST_DATE, WINDOW_MESSAGE
from eventmatch.ui.demo_scenarios import DEMOS
from eventmatch.ai.models import AgentError
from eventmatch.domain.matcher import recommend
from eventmatch.application.presentation import result_message
from tests.support import BASE, QUERY


class PolishUITests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()

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
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20)
        for key, value in {"city": "Алматы", "event_date": date(2027, 1, 1),
                           "event_type": "свадьба", "category": "Ведущий", "budget": 2000000,
                           "duration": 6.0, "language": "русский"}.items():
            app.session_state[key] = value
        app.run()
        self.assertFalse(app.exception)
        self.assertIsNone(app.date_input(key="event_date").value)
        self.assertTrue(any(WINDOW_MESSAGE in x.value for x in app.info))
        with patch("eventmatch.ui.manual.recommend") as matcher:
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
        with patch("eventmatch.infrastructure.openai_client.OpenAIBackend", return_value=backend):
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

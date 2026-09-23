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
    def app(self, review=False):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20)
        if review:
            app.query_params["review"] = "1"
        return app.run()

    def test_branding_labels_collapsed_details_and_date_picker(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "EventMatch")
        self.assertEqual([t.label for t in app.tabs], ["Подбор в чате", "Поиск по параметрам"])
        self.assertEqual(app.selectbox(key="city").label, "Локация")
        self.assertFalse(any(s.key == "demo_choice" for s in app.selectbox))
        self.assertFalse(app.table)
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
            app.button(key="search_manual").click().run()
            matcher.assert_not_called()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)

    def test_synthetic_estimated_labels_and_score_expander(self):
        app = self.app(review=True)
        app.selectbox(key="demo_choice").select(list(DEMOS)[1]).run()
        app.button(key="search_manual").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.subheader), 1)
        captions = " ".join(c.value for c in app.caption)
        self.assertIn("Синтетический профиль", captions)
        self.assertNotIn("Исходный профиль", captions)
        self.assertNotIn("восстановлена в датасете", captions)
        self.assertTrue(any(e.label == "Подробности подбора" and not e.proto.expanded for e in app.expander))

    def test_chat_api_failure_keeps_manual_fallback_working(self):
        backend = Mock()
        backend.parse.side_effect = AgentError("Чат временно недоступен. Используйте «Поиск по параметрам».")
        with patch("eventmatch.infrastructure.openai_client.OpenAIBackend", return_value=backend):
            app = self.app()
            app.chat_input[0].set_value("Нужен ведущий").run()
            self.assertFalse(app.exception)
            self.assertIsNone(app.session_state.conversation.pending)
            app.button(key="search_manual").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.subheader), 3)

    def test_no_match_presentation_retains_every_rejection_count(self):
        request = replace(QUERY, budget_kzt=1)
        result = recommend([replace(BASE, busy_dates=(QUERY.event_date,))], request)
        before = result.copy()
        text = result_message(result, request)
        self.assertIn("Подходящих вариантов не нашлось", text)
        self.assertIn("1 — заняты", text)
        self.assertIn("1 — начальная цена выше бюджета", text)
        self.assertEqual(result, before)

    def test_normal_experience_has_no_judge_controls_or_scores(self):
        app = self.app()
        self.assertFalse(app.chat_message)
        self.assertEqual(app.chat_input[0].placeholder, "Введите сообщение…")
        self.assertEqual(sum("Например:" in c.value for c in app.caption), 1)
        self.assertEqual([e.label for e in app.sidebar.expander], ["О сервисе", "Как работает подбор"])
        app.button(key="search_manual").click().run()
        self.assertEqual(len(app.subheader), 3)
        self.assertFalse(app.table)
        self.assertFalse(app.warning)
        text = " ".join(x.value for x in list(app.markdown) + list(app.caption))
        for unwanted in ("Демо-сценарии", "В каталоге 66", "Оценка соответствия", "👋", "✨"):
            self.assertNotIn(unwanted, text)

    def test_review_mode_keeps_same_results_with_collapsed_details(self):
        normal, review = self.app(), self.app(review=True)
        for app in (normal, review):
            app.button(key="search_manual").click().run()
            self.assertFalse(app.exception)
        self.assertEqual([s.value for s in normal.subheader], [s.value for s in review.subheader])
        self.assertEqual(len(review.table), 3)
        self.assertTrue(all(not e.proto.expanded for e in review.expander))


if __name__ == "__main__":
    unittest.main()

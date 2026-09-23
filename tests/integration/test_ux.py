"""Current chat-only UI, date safety and review details; no live API calls."""
import unittest
from dataclasses import asdict, replace
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from eventmatch.application.availability import WINDOW_MESSAGE
from eventmatch.ui.demo_scenarios import DEMOS
from eventmatch.ai.models import AgentError, Update
from eventmatch.domain.matcher import load_catalog, recommend
from eventmatch.paths import DEFAULT_CATALOG
from eventmatch.application.presentation import result_message
from tests.support import BASE, QUERY, ROOT, decision


class PolishUITests(unittest.TestCase):
    def setUp(self):
        self.backend = Mock()
        self.backend.explain.return_value = {}
        patcher = patch("eventmatch.infrastructure.openai_client.OpenAIBackend", return_value=self.backend)
        patcher.start()
        self.addCleanup(patcher.stop)

    def app(self, review=False):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20)
        if review:
            app.query_params["review"] = "1"
        return app.run()

    def submit(self, app, request):
        self.backend.parse.return_value = decision(updates=[
            Update(field=k, value=v, evidence=request.event_date) for k, v in asdict(request).items()
        ])
        app.chat_input[0].set_value(f"Мероприятие {request.event_date}").run()
        self.assertFalse(app.exception)

    def search(self, app, request=None):
        self.submit(app, request or next(iter(DEMOS.values())))
        app.button(key="confirm_chat").click().run()
        self.assertFalse(app.exception)

    def test_branding_chat_only_and_collapsed_information_below_chat(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "EventMatch")
        self.assertEqual(len(app.chat_input), 1)
        self.assertFalse(app.tabs)
        self.assertFalse(app.selectbox)
        self.assertFalse(app.date_input)
        self.assertFalse(app.number_input)
        self.assertFalse(app.get("form"))
        self.assertFalse(app.table)
        self.assertEqual([b.key for b in app.button], ["reset_chat"])
        self.assertEqual(app.button(key="reset_chat").label, "Новый поиск")
        self.assertTrue(app.button(key="reset_chat").disabled)
        self.assertFalse(app.sidebar.expander)
        self.assertFalse(app.sidebar.button)
        self.assertEqual([e.label for e in app.expander], ["О сервисе", "Как работает подбор"])
        elements = list(app.main)
        chat_position = next(i for i, e in enumerate(elements) if e.type == "chat_input")
        for i, element in enumerate(elements):
            if element.type == "expander":
                self.assertGreater(i, chat_position)
                self.assertFalse(element.proto.expanded)

    def test_chat_outside_calendar_window_blocks_search_until_corrected(self):
        app = self.app()
        with patch("eventmatch.application.conversation.recommend", wraps=recommend) as matcher:
            for date in ("2026-09-22", "2027-01-01"):
                with self.subTest(date=date):
                    self.submit(app, replace(QUERY, event_date=date))
                    self.assertIsNone(app.session_state.conversation.pending)
                    self.assertIsNone(app.session_state.conversation.last_result)
                    self.assertEqual(app.session_state.conversation.unresolved["event_date"], WINDOW_MESSAGE)
                    self.assertTrue(any("23.09.2026–31.12.2026" in m.value.replace("\\", "") for m in app.markdown))
                    self.assertFalse(any(b.key == "confirm_chat" for b in app.button))
                    matcher.assert_not_called()
            self.backend.parse.return_value = decision(updates=[
                Update(field="event_date", value=QUERY.event_date, evidence="14 ноября 2026")
            ])
            app.chat_input[0].set_value("14 ноября 2026").run()
            self.assertEqual(app.session_state.conversation.pending, QUERY)
            matcher.assert_not_called()
            app.button(key="confirm_chat").click().run()
            self.assertFalse(app.exception)
            matcher.assert_called_once()
            self.assertEqual(app.session_state.conversation.last_request, QUERY)

    def test_synthetic_estimated_labels_and_score_expander(self):
        app = self.app(review=True)
        self.search(app, list(DEMOS.values())[1])
        self.assertEqual([s.value for s in app.subheader], ["Тихиро Огино"])
        contractor = app.session_state.conversation.last_result["cards"][0]["contractor"]
        captions = " ".join(c.value for c in app.caption)
        self.assertIn("Синтетический профиль", captions)
        for flag, label in ((contractor.price_imputed, "Ориентировочная цена"),
                            (contractor.city_imputed, "Локация указана ориентировочно")):
            self.assertEqual(label in captions, flag)
        self.assertNotIn("Исходный профиль", captions)
        self.assertNotIn("восстановлена в датасете", captions)
        self.assertEqual(len(app.table), 1)
        self.assertTrue(any(e.label == "Подробности подбора" and not e.proto.expanded for e in app.expander))

    def test_chat_api_failure_preserves_conditions_and_allows_retry(self):
        app = self.app()
        self.submit(app, QUERY)
        draft = dict(app.session_state.conversation.draft)
        self.backend.parse.side_effect = AgentError("Чат временно недоступен. Используйте «Поиск по параметрам».")
        with patch("eventmatch.application.conversation.recommend", wraps=recommend) as matcher:
            app.chat_input[0].set_value("нет, бюджет миллион").run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state.conversation.draft, draft)
            self.assertIsNone(app.session_state.conversation.pending)
            self.assertIsNone(app.session_state.conversation.last_result)
            matcher.assert_not_called()
        text = " ".join(m.value for m in app.markdown)
        self.assertIn("Ваши условия сохранены", text)
        self.assertNotIn("Поиск по параметрам", text)
        self.assertFalse(app.subheader)
        self.assertFalse(any(b.key == "search_manual" for b in app.button))
        self.assertEqual(len(app.chat_input), 1)
        self.backend.parse.side_effect = None
        self.backend.parse.return_value = decision(updates=[Update(field="budget_kzt", value=1000000, evidence="миллион")])
        app.chat_input[0].set_value("нет, бюджет миллион").run()
        self.assertEqual(app.session_state.conversation.pending, replace(QUERY, budget_kzt=1000000))
        self.backend.explain.side_effect = AgentError("Сервис временно недоступен.")
        app.button(key="confirm_chat").click().run()
        self.assertFalse(app.exception)
        expected = recommend(load_catalog(DEFAULT_CATALOG), replace(QUERY, budget_kzt=1000000))
        self.assertEqual(app.session_state.conversation.last_result, expected)
        self.assertTrue(app.subheader)
        self.assertEqual(app.session_state.conversation.messages[-1].explanations, {})

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
        self.search(app)
        self.assertEqual(len(app.subheader), 3)
        self.assertEqual(app.chat_input[0].placeholder, "Что уточним или изменим?")
        self.assertFalse(app.table)
        self.assertFalse(app.warning)
        self.assertFalse(app.selectbox)
        self.assertFalse(app.tabs)
        self.assertEqual([e.label for e in app.expander], ["О сервисе", "Как работает подбор"])
        text = " ".join(x.value for x in list(app.markdown) + list(app.caption))
        for unwanted in ("Демо-сценарии", "В каталоге 66", "Соответствие условиям:", "Поиск по параметрам", "👋", "✨"):
            self.assertNotIn(unwanted, text)

    def test_review_mode_keeps_same_results_with_collapsed_details(self):
        normal, review = self.app(), self.app(review=True)
        for app in (normal, review):
            self.search(app)
            self.assertFalse(app.selectbox)
            self.assertFalse(app.tabs)
        self.assertEqual(normal.session_state.conversation.last_result, review.session_state.conversation.last_result)
        self.assertEqual([s.value for s in normal.subheader], ["Сон Гоку", "Хаул", "Эмилия"])
        self.assertEqual([s.value for s in normal.subheader], [s.value for s in review.subheader])
        self.assertFalse(normal.table)
        self.assertEqual(len(review.table), 3)
        self.assertEqual([e.label for e in review.expander],
                         ["Условия этого поиска", "Подробности подбора", "О сервисе", "Как работает подбор"])
        self.assertTrue(all(not e.proto.expanded for e in review.expander))
        for table, card in zip(review.table, review.session_state.conversation.last_result["cards"]):
            self.assertEqual(table.value.to_dict("records"),
                             [{"Критерий": k, "Баллы": round(v, 1)} for k, v in card["score_parts"].items()])


if __name__ == "__main__":
    unittest.main()

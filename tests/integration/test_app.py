"""Chat-only product flows using mocked extraction and the real matcher."""
import unittest
from dataclasses import asdict
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from eventmatch.ai.models import Update
from eventmatch.ui.demo_scenarios import DEMOS
from tests.support import ROOT, decision


class AppTests(unittest.TestCase):
    def test_all_chat_outcomes_and_input_changes(self):
        backend = Mock()
        backend.explain.return_value = {}
        expected = [
            ("SUCCESS", ["Сон Гоку", "Хаул", "Эмилия"]),
            ("SUCCESS", ["Тихиро Огино"]),
            ("NO_MATCH", []),
            ("CATEGORY_NOT_FOUND", []),
        ]
        with patch("eventmatch.infrastructure.openai_client.OpenAIBackend", return_value=backend):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
            for request, (status, names) in zip(DEMOS.values(), expected):
                with self.subTest(status=status, category=request.category):
                    if not app.button(key="reset_chat").disabled:
                        app.button(key="reset_chat").click().run()
                    backend.parse.return_value = decision(updates=[
                        Update(field=k, value=v, evidence="2026") for k, v in asdict(request).items()
                    ])
                    app.chat_input[0].set_value("Мероприятие 2026").run()
                    self.assertFalse(app.exception)
                    self.assertEqual(app.session_state.conversation.pending, request)
                    self.assertIsNone(app.session_state.conversation.last_result)
                    self.assertFalse(app.subheader)
                    app.button(key="confirm_chat").click().run()
                    self.assertFalse(app.exception)
                    self.assertEqual(app.session_state.conversation.last_result["status"], status)
                    self.assertEqual([s.value for s in app.subheader], names)
                    if request.category == "Флорист":
                        self.assertTrue(any("Синтетический профиль" in c.value for c in app.caption))
                    if status == "NO_MATCH":
                        self.assertEqual(app.session_state.conversation.last_result["rejections"],
                                         {"busy": 5, "event_format": 4, "budget": 10})
                        text = " ".join(m.value for m in app.markdown)
                        for fragment in ("не нашлось", "5 — заняты", "4 — не поддерживают", "10 — начальная цена"):
                            self.assertIn(fragment, text)
                    if status == "CATEGORY_NOT_FOUND":
                        self.assertTrue(any("пока нет подрядчиков" in m.value for m in app.markdown))

            # Corrections require confirmation; previous results stay in chat history.
            app.button(key="reset_chat").click().run()
            request = next(iter(DEMOS.values()))
            backend.parse.return_value = decision(updates=[
                Update(field=k, value=v, evidence="2026") for k, v in asdict(request).items()
            ])
            app.chat_input[0].set_value("Мероприятие 2026").run()
            app.button(key="confirm_chat").click().run()
            self.assertEqual(app.session_state.conversation.last_result["status"], "SUCCESS")
            backend.parse.return_value = decision(updates=[Update(field="budget_kzt", value=1, evidence="1")])
            previous = app.session_state.conversation.last_result
            app.chat_input[0].set_value("Бюджет 1").run()
            self.assertEqual(app.session_state.conversation.pending.budget_kzt, 1)
            self.assertEqual(app.session_state.conversation.last_result, previous)
            app.button(key="confirm_chat").click().run()
            self.assertFalse(app.exception)
            self.assertIsNone(app.session_state.conversation.pending)
            self.assertEqual(app.session_state.conversation.last_request.budget_kzt, 1)
            self.assertEqual(app.session_state.conversation.last_result["status"], "NO_MATCH")
            self.assertTrue(any("не нашлось" in m.value for m in app.markdown))
            self.assertEqual([s.value for s in app.subheader], expected[0][1])
            app.button(key="reset_chat").click().run()
            self.assertIsNone(app.session_state.conversation.last_result)
            self.assertFalse(app.chat_message)
            self.assertFalse(app.subheader)
            self.assertTrue(app.button(key="reset_chat").disabled)


if __name__ == "__main__":
    unittest.main()

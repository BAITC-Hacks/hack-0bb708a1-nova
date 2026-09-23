import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from agent_models import TurnDecision, Update
from test_conversation import complete_decision, decision


class ChatUITests(unittest.TestCase):
    def test_confirm_followup_and_reset(self):
        backend = Mock()
        backend.parse.return_value = complete_decision()
        backend.explain.return_value = {}
        with patch("llm_client.OpenAIBackend", return_value=backend):
            app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=20).run()
            self.assertFalse(app.exception)
            app.chat_input[0].set_value("Мероприятие 2026").run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.subheader), 0)
            self.assertEqual(app.button(key="confirm_chat").label, "Подтвердить и найти")
            app.button(key="confirm_chat").click().run()
            self.assertFalse(app.exception)
            self.assertIsNotNone(app.session_state.conversation.last_result)
            backend.parse.assert_called_once()
            backend.parse.return_value = decision(updates=[Update(field="budget_kzt", value=1, evidence="1")])
            app.chat_input[0].set_value("Бюджет 1").run()
            self.assertEqual(app.session_state.conversation.pending.budget_kzt, 1)
            app.button(key="confirm_chat").click().run()
            self.assertEqual(app.session_state.conversation.last_result["status"], "NO_MATCH")
            app.button(key="reset_chat").click().run()
            self.assertIsNone(app.session_state.conversation.last_result)
            self.assertEqual(len(app.chat_message), 1)

    def test_off_topic_does_not_produce_cards(self):
        backend = Mock()
        backend.parse.return_value = TurnDecision(intent="off_topic", updates=[], ambiguities=[], reply="Давайте вернёмся к подбору.")
        with patch("llm_client.OpenAIBackend", return_value=backend):
            app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=20).run()
            app.chat_input[0].set_value("Расскажи про космос").run()
            self.assertFalse(app.exception)
            self.assertIsNone(app.session_state.conversation.pending)
            self.assertEqual(len(app.subheader), 0)
            backend.explain.assert_not_called()


if __name__ == "__main__":
    unittest.main()

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from openai import APIConnectionError, AuthenticationError, RateLimitError

from eventmatch.ai.models import CardVerdict, TurnDecision, VerifiedCards, WrittenCard, WrittenCards
from eventmatch.infrastructure.openai_client import AgentError, OpenAIBackend
from eventmatch.domain.matcher import recommend
from tests.support import BASE, QUERY


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        with patch("eventmatch.infrastructure.openai_client.configuration", return_value=("test-placeholder", "test-model")), patch("eventmatch.infrastructure.openai_client.OpenAI", return_value=self.client):
            self.backend = OpenAIBackend()

    def test_missing_key_is_safe(self):
        with patch("eventmatch.infrastructure.openai_client.configuration", return_value=("", "test-model")), self.assertRaises(AgentError):
            OpenAIBackend()

    def test_parse_uses_schema_no_storage_and_no_tools(self):
        parsed = TurnDecision(intent="greeting", updates=[], ambiguities=[], reply="Здравствуйте!")
        self.client.responses.parse.return_value = SimpleNamespace(status="completed", output_parsed=parsed)
        self.assertEqual(self.backend.parse({"latest_message": "Привет"}), parsed)
        kwargs = self.client.responses.parse.call_args.kwargs
        self.assertFalse(kwargs["store"])
        self.assertNotIn("tools", kwargs)
        self.assertIs(kwargs["text_format"], TurnDecision)

    def test_refusal_and_truncation_fail_closed(self):
        for status in ("completed", "incomplete"):
            self.client.responses.parse.return_value = SimpleNamespace(status=status, output_parsed=None)
            with self.assertRaises(AgentError):
                self.backend.parse({})

    def test_raw_api_errors_not_exposed(self):
        request = httpx.Request("POST", "https://api.openai.com/v1/responses")
        response = httpx.Response(429, request=request)
        errors = [APIConnectionError(request=request),
                  RateLimitError("RAW SECRET", response=response, body={"secret": "private"}),
                  AuthenticationError("RAW SECRET", response=response, body={"secret": "private"})]
        for error in errors:
            self.client.responses.parse.side_effect = error
            with self.assertRaises(AgentError) as raised:
                self.backend.parse({})
            self.assertNotIn("RAW SECRET", str(raised.exception))
            self.assertNotIn("private", str(raised.exception))

    def test_wrong_id_or_invented_quote_rejected_before_verifier(self):
        for cid, quote in [("unknown", BASE.description), (BASE.id, "Выдуманная скидка")]:
            self.backend._call = Mock(return_value=WrittenCards(cards=[WrittenCard(id=cid, explanation="Объяснение", description_quote=quote)]))
            self.assertEqual(self.backend.explain(QUERY, recommend([BASE], QUERY)), {})
            self.backend._call.assert_called_once()

    def test_verifier_rejection_falls_back(self):
        written = WrittenCards(cards=[WrittenCard(id=BASE.id, explanation="Неподтверждённая скидка.", description_quote=BASE.description)])
        self.backend._call = Mock(side_effect=[written, VerifiedCards(cards=[CardVerdict(id=BASE.id, supported=False)])])
        self.assertEqual(self.backend.explain(QUERY, recommend([BASE], QUERY)), {})

    def test_only_grounded_narration_returned(self):
        explanation = "Подтверждённые факты."
        written = WrittenCards(cards=[WrittenCard(id=BASE.id, explanation=explanation, description_quote=BASE.description)])
        self.backend._call = Mock(side_effect=[written, VerifiedCards(cards=[CardVerdict(id=BASE.id, supported=True)])])
        self.assertEqual(self.backend.explain(QUERY, recommend([BASE], QUERY)), {BASE.id: explanation})
        payload = self.backend._call.call_args_list[0].args[1]
        self.assertNotIn("busy_dates", payload["profiles"][0])
        self.assertNotIn("history", payload)


if __name__ == "__main__":
    unittest.main()

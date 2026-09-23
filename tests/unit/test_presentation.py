"""Product copy stays compact while preserving matching facts and caveats."""
import unittest
from dataclasses import asdict, replace
from unittest.mock import Mock

from eventmatch.ai.models import Update
from eventmatch.application.conversation import Conversation, handle_message
from eventmatch.application.presentation import card_explanation, confirmation_text, outcome_text, summary
from eventmatch.domain.matcher import recommend
from tests.support import BASE, QUERY, decision


class PresentationTests(unittest.TestCase):
    def test_compact_confirmation_preserves_every_provided_condition(self):
        self.assertEqual(summary(QUERY),
                         "Алматы\n14 ноября 2026\nСвадьба · Ведущий\nДо 800 000 ₸\n6 ч · русский")
        self.assertEqual(confirmation_text(QUERY), "Проверьте условия\n\n" + summary(QUERY))

    def test_missing_optional_fields_do_not_block_confirmation(self):
        request = replace(QUERY, language=None, duration_hours=None)
        backend = Mock()
        backend.parse.return_value = decision(updates=[
            Update(field=key, value=value, evidence="2026")
            for key, value in asdict(request).items() if value is not None
        ])
        state = Conversation()
        handle_message(state, "Мероприятие 2026", [BASE], backend)
        self.assertEqual(state.pending, request)
        self.assertFalse(state.unresolved)
        self.assertEqual(len(summary(request).splitlines()), 4)
        backend.explain.assert_not_called()

    def test_fallback_uses_price_date_and_exact_profile_excerpt(self):
        result = recommend([BASE], QUERY)
        before = recommend([BASE], QUERY)
        text = card_explanation(result["cards"][0]["contractor"], QUERY)
        for fact in ("14 ноября", "от 600 000 ₸", "по календарю", BASE.description):
            self.assertIn(fact, text.lower() if fact == "по календарю" else text)
        self.assertEqual(result, before)

    def test_language_mismatch_is_never_hidden_by_short_copy(self):
        contractor = replace(BASE, languages=("казахский",), max_hours=None)
        text = card_explanation(contractor, QUERY)
        self.assertIn("Язык «русский» в профиле не указан", text)
        self.assertNotIn("без ограничений", text)

    def test_no_match_keeps_all_reasons_and_only_suggests_relevant_changes(self):
        contractor = replace(BASE, busy_dates=(QUERY.event_date,), price_from_kzt=900000,
                             event_formats=("корпоратив",), max_hours=2)
        result = recommend([contractor], QUERY)
        text = outcome_text(result, QUERY)
        self.assertEqual(text.count("1 —"), 4)
        self.assertIn("другую дату", text)
        self.assertIn("другой бюджет", text)
        self.assertEqual(result, recommend([contractor], QUERY))

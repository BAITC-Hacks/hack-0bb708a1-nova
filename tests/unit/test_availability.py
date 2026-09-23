"""Product date-window safety tests. No API calls required."""
import unittest
from dataclasses import asdict, replace
from unittest.mock import Mock, patch


from eventmatch.ai.models import Ambiguity, Update
from eventmatch.application.availability import DateOutsideWindow, FIRST_DATE, LAST_DATE, WINDOW_MESSAGE, validate_event_date
from eventmatch.application.conversation import Conversation, confirm_search, handle_message
from eventmatch.domain.matcher import recommend
from tests.support import decision
from tests.support import BASE, QUERY


class DateWindowTests(unittest.TestCase):
    def test_inclusive_boundaries(self):
        for day in (FIRST_DATE, LAST_DATE):
            self.assertEqual(validate_event_date(day.isoformat()), day)
            request = replace(QUERY, event_date=day.isoformat())
            state = Conversation(draft=asdict(request), pending=request)
            backend = Mock()
            backend.explain.return_value = {}
            with patch("eventmatch.application.conversation.recommend", wraps=recommend) as matcher:
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
                    with patch("eventmatch.application.conversation.recommend") as matcher:
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
        with patch("eventmatch.application.conversation.recommend") as matcher:
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


if __name__ == "__main__":
    unittest.main()

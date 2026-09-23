"""Server-only OpenAI adapter. No secrets, raw API errors or prompts in the UI."""
import json
import os
from dataclasses import asdict
from eventmatch.paths import ENV_FILE

from dotenv import load_dotenv
from openai import APIConnectionError, APIError, APITimeoutError, AuthenticationError, OpenAI, RateLimitError
from pydantic import ValidationError

from eventmatch.ai.models import AgentError, TurnDecision, VerifiedCards, WrittenCards
from eventmatch.ai.prompts import EXPLAIN_PROMPT, PARSE_PROMPT, VERIFY_PROMPT


def configuration():
    load_dotenv(ENV_FILE, override=False)
    return os.getenv("OPENAI_API_KEY", "").strip(), os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()


class OpenAIBackend:
    def __init__(self):
        key, self.model = configuration()
        if not key:
            raise AgentError("Чат пока недоступен. Воспользуйтесь вкладкой «Поиск по параметрам».")
        # Explicit official endpoint: an unrelated inherited proxy must not receive the key.
        self.client = OpenAI(api_key=key, base_url="https://api.openai.com/v1", timeout=25.0, max_retries=0)

    def _call(self, prompt, payload, schema):
        try:
            response = self.client.responses.parse(
                model=self.model,
                instructions=prompt,
                input=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                text_format=schema, max_output_tokens=2200, store=False,
            )
            if response.status != "completed" or response.output_parsed is None:
                raise AgentError("Не удалось надёжно разобрать ответ. Переформулируйте запрос; поиск не запущен.")
            return response.output_parsed
        except AuthenticationError:
            raise AgentError("Чат временно недоступен. Вы можете продолжить во вкладке «Поиск по параметрам».") from None
        except RateLimitError:
            raise AgentError("Сервис чата сейчас занят. Попробуйте позже или используйте «Поиск по параметрам».") from None
        except (APITimeoutError, APIConnectionError):
            raise AgentError("Чат не ответил вовремя. Ваши условия сохранены; повторите сообщение или используйте «Поиск по параметрам».") from None
        except (APIError, ValidationError, ValueError):
            raise AgentError("Не удалось получить корректный ответ сервиса чата. Условия не изменены; попробуйте ещё раз.") from None

    def parse(self, payload):
        return self._call(PARSE_PROMPT, payload, TurnDecision)

    def explain(self, request, result):
        # Do not transmit full busy calendars, irrelevant catalog rows or conversation history.
        profiles = []
        for card in result["cards"]:
            profile = asdict(card["contractor"])
            profile.pop("busy_dates")
            profile["available_on_requested_date_in_catalog"] = True
            profiles.append(profile)
        payload = {"request": asdict(request), "profiles": profiles}
        written = self._call(EXPLAIN_PROMPT, payload, WrittenCards)
        ids = [c["contractor"].id for c in result["cards"]]
        if [c.id for c in written.cards] != ids:
            return {}
        # An exact source quote is a deterministic prerequisite for accepting narration.
        for generated, original in zip(written.cards, profiles):
            if generated.description_quote not in original["description"]:
                return {}
            if any(marker in generated.explanation for marker in ("http:", "https:", "<", ">", "```")):
                return {}
        verdicts = self._call(VERIFY_PROMPT, {**payload, "proposed": written.model_dump()}, VerifiedCards)
        if [v.id for v in verdicts.cards] != ids:
            return {}
        return {c.id: c.explanation for c, v in zip(written.cards, verdicts.cards) if v.supported}

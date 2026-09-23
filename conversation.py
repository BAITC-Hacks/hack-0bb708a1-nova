"""Session-only state machine. The model proposes; Python validates and dispatches.

Only confirm_search() calls the unchanged matcher. LLMs have no matching tool.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from agent_models import TurnDecision
from availability_window import DateOutsideWindow, WINDOW_MESSAGE, validate_event_date
from llm_client import AgentError
from matcher import Request, iso_date, money, normalized, recommend
from presentation import result_message

REQUIRED = ("city", "event_date", "event_type", "category", "budget_kzt")
FIELDS = REQUIRED + ("duration_hours", "language")
QUESTIONS = {
    "city": "В каком городе пройдёт мероприятие?",
    "event_date": "На какую дату ищем подрядчика? Укажите день, месяц и год.",
    "event_type": "Какое мероприятие планируете: свадьбу, корпоратив или другой формат?",
    "category": "Кого подбираем: ведущего, фотографа или другого подрядчика?",
    "budget_kzt": "Какой максимальный бюджет на этого подрядчика в тенге?",
    "duration_hours": "Сколько часов нужен подрядчик? Можно не задавать продолжительность.",
    "language": "Какой язык предпочитаете? Можно указать, что язык не важен.",
}
INTRO = "Расскажите, что вы планируете 👋"
REDIRECTS = {
    "off_topic": "Я помогаю с подбором подрядчиков для мероприятий. Расскажите о вашем событии — город, дата и кого нужно найти.",
    "nonsense": "Не совсем поняла сообщение. Напишите, кого ищете и для какого мероприятия — разберём условия вместе.",
    "abusive": "Давайте вернёмся к задаче. Я могу помочь подобрать подрядчика — какие условия нужно учесть?",
    "injection": "Я могу помочь с подбором подрядчиков по условиям каталога. Расскажите о мероприятии — эти условия проверяются для каждого результата.",
    "unsafe": "С таким запросом я помочь не могу. Могу подобрать подрядчиков для безопасного мероприятия — расскажите, что планируете.",
}
CONFIRMATIONS = {"да", "да ищи", "да ищите", "ищи", "ищите", "подтверждаю", "все верно", "верно", "да все верно", "все верно ищи", "давай искать", "найти подрядчиков"}
INJECTION = re.compile(
    r"(?:игнорируй|забудь|обойди|отмени).{0,60}(?:инструкц|правил|фильтр|ограничен|роль)|"
    r"(?:ignore|disregard|override).{0,60}(?:instruction|rule|filter|prompt)|"
    r"(?:system\s*prompt|системн\w*\s+промпт|OPENAI_API_KEY|sk-[a-zA-Z0-9_-]{15,})",
    re.I | re.S,
)


@dataclass
class Message:
    role: str
    text: str
    result: dict | None = None
    request: Request | None = None
    explanation_source: str | None = None


@dataclass
class Conversation:
    draft: dict = field(default_factory=lambda: dict.fromkeys(FIELDS))
    unresolved: dict = field(default_factory=dict)
    messages: list[Message] = field(default_factory=lambda: [Message("assistant", INTRO)])
    context: list[dict] = field(default_factory=list)
    pending: Request | None = None
    last_request: Request | None = None
    last_result: dict | None = None
    explanation_cache: dict = field(default_factory=dict)

    def add(self, role, text, **kwargs):
        # Bound in-session memory; the structured draft survives context truncation.
        self.messages.append(Message(role, text, **kwargs))
        self.messages = self.messages[-80:]


def summary(request: Request) -> str:
    parts = [f"Локация: {request.city}", f"Дата: {iso_date(request.event_date).strftime('%d.%m.%Y')}",
             f"Мероприятие: {request.event_type}", f"Категория: {request.category}",
             f"Бюджет: до {money(request.budget_kzt)}"]
    if request.duration_hours is not None:
        parts.append(f"Продолжительность: {request.duration_hours:g} ч")
    if request.language:
        parts.append(f"Предпочитаемый язык: {request.language}")
    return "\n".join(parts)


def confirmation_text(request):
    return "Проверим, правильно ли я поняла:\n\n" + summary(request) + "\n\nВсё верно — искать по этим условиям? Можно подтвердить или поправить детали."


def safe_reply(text):
    return bool(text and re.search(r"[а-яА-ЯёЁ]", text) and not INJECTION.search(text)
                and not re.search(r"https?://|<[^>]*>", text))


def validated_value(update, draft, catalog):
    value, key = update.value, update.field
    if value is None:
        return None
    if key in ("budget_kzt", "duration_hours"):
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
            raise ValueError(QUESTIONS[key])
        return value
    if not isinstance(value, str) or not value.strip() or len(value) > 120:
        raise ValueError(QUESTIONS[key])
    value = value.strip()
    if key == "event_date":
        iso_date(value)
        # A model may not silently invent a year for the first date.
        if not draft.get("event_date") and not re.search(r"\b20\d{2}\b|сегодня|завтра", update.evidence, re.I):
            raise ValueError("Уточните, пожалуйста, год мероприятия.")
        validate_event_date(value)
    values = {
        "city": {c.city for c in catalog},
        "category": {v for c in catalog for v in c.categories},
        "event_type": {v for c in catalog for v in c.event_formats},
        "language": {v for c in catalog for v in c.languages},
    }.get(key, set())
    return next((v for v in sorted(values) if normalized(v) == normalized(value)), value)


def build_payload(state, text, catalog):
    return {
        "today": datetime.now(ZoneInfo("Asia/Almaty")).date().isoformat(),
        "draft": state.draft,
        "unresolved": state.unresolved,
        "awaiting_confirmation": state.pending is not None,
        "history": state.context[-12:],
        "last_result": None if state.last_result is None else {
            "status": state.last_result["status"], "rejections": state.last_result["rejections"],
            "eligible_count": state.last_result["eligible_count"],
        },
        "catalog_values": {
            "cities": sorted({c.city for c in catalog}),
            "categories": sorted({v for c in catalog for v in c.categories}),
            "event_types": sorted({v for c in catalog for v in c.event_formats}),
            "languages": sorted({v for c in catalog for v in c.languages}),
        },
        "latest_message": text,
    }


def handle_message(state: Conversation, text: str, catalog, backend):
    text = text.strip()
    if not text:
        return
    # Never put accidentally pasted token values in the UI or model context.
    visible = re.sub(r"sk-[a-zA-Z0-9_-]{15,}", "[ключ скрыт]", text)
    state.add("user", visible[:4000])
    if len(text) > 4000:
        state.pending = None
        state.add("assistant", "Сообщение слишком длинное. Кратко опишите мероприятие и нужного подрядчика — до 4000 символов.")
        return
    if INJECTION.search(text):
        state.pending = None
        state.add("assistant", REDIRECTS["injection"])
        return
    confirmation = re.sub(r"[^а-яa-z0-9\s]", "", normalized(text))
    if confirmation in CONFIRMATIONS and state.pending is not None:
        confirm_search(state, catalog, backend)
        return
    if normalized(text) in ("начать заново", "новый поиск", "сбросить"):
        reset(state)
        return
    try:
        decision = backend.parse(build_payload(state, text, catalog))
        if not isinstance(decision, TurnDecision):
            raise AgentError("Не удалось надёжно разобрать сообщение. Попробуйте переформулировать; условия не изменены.")
    except AgentError as exc:
        state.pending = None
        state.add("assistant", str(exc))
        return
    if decision.intent in REDIRECTS:
        state.pending = None
        state.add("assistant", REDIRECTS[decision.intent])
        return
    if decision.intent == "reset":
        reset(state)
        return
    if decision.intent in ("greeting", "question"):
        state.add("assistant", decision.reply if safe_reply(decision.reply) else INTRO)
        return
    if decision.intent == "confirm":
        # Natural affirmatives are accepted only for the current, unchanged snapshot.
        if state.pending and not decision.updates and not decision.ambiguities:
            confirm_search(state, catalog, backend)
        else:
            state.pending = None
            state.add("assistant", "Сначала уточним условия. " + next_question(state))
        return

    state.pending = None
    fields_seen = set()
    # Validate the complete patch before applying any mutation (atomic on invalid evidence).
    for update in decision.updates:
        if update.field in fields_seen or not update.evidence.strip() or update.evidence not in text:
            state.add("assistant", "Не удалось однозначно связать условия с вашим сообщением. Уточните, пожалуйста, что нужно изменить.")
            return
        fields_seen.add(update.field)
    for update in decision.updates:
        try:
            value = validated_value(update, state.draft, catalog)
        except DateOutsideWindow:
            state.unresolved[update.field] = WINDOW_MESSAGE
            continue
        except ValueError:
            state.unresolved[update.field] = QUESTIONS[update.field]
            continue
        state.draft[update.field] = value
        state.unresolved.pop(update.field, None)
    for ambiguity in decision.ambiguities:
        if ambiguity.field == "event_date" and state.unresolved.get("event_date") == WINDOW_MESSAGE:
            continue
        state.unresolved[ambiguity.field] = ambiguity.question if safe_reply(ambiguity.question) else QUESTIONS[ambiguity.field]

    missing = [key for key in REQUIRED if state.draft[key] is None]
    if state.unresolved or missing:
        # LLM supplies natural phrasing, but cannot skip the deterministic missing-fields check.
        if state.unresolved:
            reply = WINDOW_MESSAGE if state.unresolved.get("event_date") == WINDOW_MESSAGE else next(iter(state.unresolved.values()))
        else:
            reply = decision.reply if safe_reply(decision.reply) and "?" in decision.reply else QUESTIONS[missing[0]]
        state.add("assistant", reply)
    else:
        try:
            validate_event_date(state.draft["event_date"])
            state.pending = Request(**state.draft)
        except DateOutsideWindow:
            state.unresolved["event_date"] = WINDOW_MESSAGE
            state.add("assistant", WINDOW_MESSAGE)
            return
        except ValueError:
            state.add("assistant", "Проверьте дату, бюджет и продолжительность: условия пока не удалось подтвердить.")
            return
        state.add("assistant", confirmation_text(state.pending))
    state.context.extend([{"role": "user", "content": text}, {"role": "assistant", "content": state.messages[-1].text}])
    state.context = state.context[-12:]


def next_question(state):
    if state.unresolved:
        return next(iter(state.unresolved.values()))
    return next((QUESTIONS[k] for k in REQUIRED if state.draft[k] is None), "Укажите, что хотите изменить, или попросите повторить поиск.")


def reset(state):
    state.draft = dict.fromkeys(FIELDS)
    state.unresolved.clear()
    state.context.clear()
    state.pending = state.last_request = state.last_result = None
    state.explanation_cache.clear()
    state.add("assistant", "Начнём новый подбор. " + INTRO)


def outcome_text(result, request):
    text = result_message(result, request)
    if result["status"] == "NO_MATCH":
        suggestions = []
        for key, suggestion in (("busy", "другую дату"), ("budget", "другой бюджет"),
                                ("duration", "меньшую продолжительность"), ("event_format", "другой формат")):
            if result["rejections"].get(key):
                suggestions.append(suggestion)
        text += " Если ваши планы позволяют, можем проверить " + ", ".join(suggestions) + ". Что хотите изменить?"
    elif result["status"] == "CATEGORY_NOT_FOUND":
        text += " Можем проверить другую категорию или локацию — что вам подходит?"
    else:
        text += " Можно уточнить бюджет, дату или другие условия — я сделаю новый подбор."
    return text


def confirm_search(state, catalog, backend):
    request = state.pending
    if request is None or state.unresolved or asdict(request) != state.draft:
        state.pending = None
        state.add("assistant", "Сначала нужно подтвердить актуальные условия. " + next_question(state))
        return
    try:
        validate_event_date(request.event_date)
    except DateOutsideWindow:
        state.pending = None
        state.unresolved["event_date"] = WINDOW_MESSAGE
        state.add("assistant", WINDOW_MESSAGE)
        return
    state.pending = None  # Consume confirmation before dispatch; reruns cannot repeat it.
    result = recommend(catalog, request)
    source = "facts"
    if result["cards"]:
        cache_key = (request, tuple(c["contractor"] for c in result["cards"]))
        explanations = state.explanation_cache.get(cache_key)
        if explanations is None:
            try:
                explanations = backend.explain(request, result)
            except AgentError:
                explanations = {}
            if explanations:
                if len(state.explanation_cache) >= 20:
                    state.explanation_cache.pop(next(iter(state.explanation_cache)))
                state.explanation_cache[cache_key] = explanations
        for card in result["cards"]:
            if card["contractor"].id in explanations:
                card["explanation"] = explanations[card["contractor"].id]
                source = "mixed"
        if len(explanations) == len(result["cards"]):
            source = "ai"
    state.last_request, state.last_result = request, result
    text = outcome_text(result, request)
    state.add("assistant", text, result=result, request=request, explanation_source=source)
    state.context.extend([{"role": "assistant", "content": "Условия подтверждены. " + summary(request)},
                          {"role": "assistant", "content": text}])
    state.context = state.context[-12:]

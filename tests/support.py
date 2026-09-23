"""Shared deterministic fixtures; no API calls or test cases."""
from dataclasses import asdict
from pathlib import Path
from eventmatch.ai.models import TurnDecision, Update
from eventmatch.domain.matcher import Contractor, Request

ROOT = Path(__file__).resolve().parents[1]

BASE = Contractor("a", "Тестовый ведущий", ("Ведущий",), "Алматы", 600_000,
                  ("свадьба",), ("русский",), 8, (),
                  "Ведущий: свадьба, интерактивные игры и импровизация.", True, False, False)
QUERY = Request("Алматы", "2026-11-14", "свадьба", "Ведущий", 800_000, 6, "русский")


def decision(intent="request", updates=None, ambiguities=None, reply="Какой бюджет в тенге?"):
    return TurnDecision(intent=intent, updates=updates or [], ambiguities=ambiguities or [], reply=reply)


def complete_decision():
    return decision(updates=[Update(field=k, value=v, evidence="2026") for k, v in asdict(QUERY).items()])



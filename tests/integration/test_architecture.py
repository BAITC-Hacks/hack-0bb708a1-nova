"""Regression checks for layer boundaries, state lifecycle and unchanged facts."""
import ast
import subprocess
import sys
import unittest
from dataclasses import asdict
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from eventmatch.ai.models import AgentError, Ambiguity, Update
from eventmatch.application.conversation import Conversation, confirm_search, handle_message
from eventmatch.paths import DEFAULT_CATALOG
from eventmatch.ui.demo_scenarios import DEMOS
from eventmatch.domain.matcher import load_catalog, recommend
from tests.support import decision
from tests.support import BASE, QUERY
from eventmatch.ui.state import apply_demo, get_conversation, initialize_manual, new_conversation

from tests.support import ROOT


def imported_modules(path):
    """Inspect ordinary imports, including relative and from-package imports."""
    from importlib.util import resolve_name

    modules = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                package = ".".join(path.parent.relative_to(ROOT / "src").parts)
                module = resolve_name("." * node.level + module, package)
            modules.add(module)
            modules.update(f"{module}.{alias.name}" for alias in node.names)
    return modules


class ArchitectureTests(unittest.TestCase):
    def test_agent_imports_without_ui_or_provider(self):
        code = '''
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'streamlit', 'openai', 'dotenv'} or name.startswith('eventmatch.infrastructure'):
        raise AssertionError('Agent imported an outer layer: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from eventmatch.application import conversation
from eventmatch.ui import state
assert conversation.Conversation().pending is None
'''
        subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True, capture_output=True)

    def test_local_dependencies_are_acyclic(self):
        sources = {".".join(p.relative_to(ROOT / "src").with_suffix("").parts).removesuffix(".__init__"): p
                   for p in (ROOT / "src/eventmatch").rglob("*.py")}
        sources["app"] = ROOT / "app.py"
        graph = {name: imported_modules(path) & sources.keys() for name, path in sources.items()}

        def visit(name, ancestors):
            self.assertNotIn(name, ancestors, f"Circular dependency through {name}")
            for child in graph[name]:
                visit(child, ancestors | {name})
        for name in graph:
            visit(name, set())

    def test_package_dependency_boundaries(self):
        allowed = {
            "domain": {"domain"},
            "application": {"application", "domain", "ai"},
            "ai": {"ai"},
            "infrastructure": {"infrastructure", "ai", "domain", "paths"},
            "ui": {"ui", "application", "domain", "ai"},
            "paths": {"paths"},
        }
        for path in (ROOT / "src/eventmatch").rglob("*.py"):
            layer = path.relative_to(ROOT / "src/eventmatch").parts[0].removesuffix(".py")
            dependencies = imported_modules(path)
            for dependency in dependencies:
                if dependency.startswith("eventmatch.") and layer in allowed:
                    self.assertIn(dependency.split(".")[1], allowed[layer], f"{path}: {dependency}")
                external = dependency.split(".")[0]
                if layer != "ui":
                    self.assertNotEqual(external, "streamlit", str(path))
                if layer != "infrastructure":
                    self.assertNotIn(external, {"openai", "dotenv"}, str(path))

    def test_wording_never_overwrites_matcher_facts(self):
        state = Conversation(draft=asdict(QUERY), pending=QUERY)
        backend = Mock()
        backend.explain.return_value = {BASE.id: "Проверенное объяснение.", "unknown": "Лишний подрядчик"}
        confirm_search(state, [BASE], backend)
        expected = recommend([BASE], QUERY)
        self.assertEqual(state.last_result, expected)
        self.assertEqual(state.messages[-1].result, expected)
        self.assertEqual(state.messages[-1].explanations, {BASE.id: "Проверенное объяснение."})

    def test_adapter_cannot_mutate_selected_results(self):
        state = Conversation(draft=asdict(QUERY), pending=QUERY)
        backend = Mock()

        def attempt_mutation(request, result):
            result["status"] = "NO_MATCH"
            result["rejections"]["busy"] = 100
            result["cards"][0]["score"] = -999
            result["cards"].clear()
            return {"unknown": "Посторонний подрядчик"}

        backend.explain.side_effect = attempt_mutation
        confirm_search(state, [BASE], backend)
        self.assertEqual(state.last_result, recommend([BASE], QUERY))
        self.assertEqual(state.messages[-1].explanations, {})

    def test_explanation_failure_preserves_facts(self):
        state = Conversation(draft=asdict(QUERY), pending=QUERY)
        backend = Mock()
        backend.explain.side_effect = AgentError("Сервис временно недоступен.")
        confirm_search(state, [BASE], backend)
        self.assertEqual(state.last_result, recommend([BASE], QUERY))
        self.assertEqual(state.messages[-1].explanations, {})

    def test_session_helpers_preserve_manual_values_on_chat_reset(self):
        session = {"demo_choice": next(iter(DEMOS))}
        self.assertIsNone(initialize_manual(session))
        state = get_conversation(session)
        self.assertIs(get_conversation(session), state)
        state.draft["city"] = "Астана"
        session["budget"] = 123456
        new_conversation(session)
        self.assertIsNot(get_conversation(session), state)
        self.assertIsNone(get_conversation(session).draft["city"])
        self.assertEqual(session["budget"], 123456)
        apply_demo(session)
        self.assertEqual(session["budget"], next(iter(DEMOS.values())).budget_kzt)

    def test_multiturn_correction_cheaper_and_date_change(self):
        state, backend = Conversation(), Mock()
        backend.explain.return_value = {}

        def send(text, changes=(), ambiguities=()):
            backend.parse.return_value = decision(
                updates=[Update(field=k, value=v, evidence=e) for k, v, e in changes],
                ambiguities=list(ambiguities),
            )
            handle_message(state, text, [BASE], backend)

        send("Ищу ведущего в Алматы", [("category", "Ведущий", "ведущего"), ("city", "Алматы", "Алматы")])
        self.assertIsNone(state.pending)
        send("На свадьбу 14 ноября 2026 до 800 тысяч", [
            ("event_type", "свадьба", "свадьбу"), ("event_date", "2026-11-14", "14 ноября 2026"),
            ("budget_kzt", 800000, "800 тысяч"),
        ])
        self.assertIsNotNone(state.pending)
        send("нет, бюджет миллион", [("budget_kzt", 1000000, "миллион")])
        self.assertEqual(state.pending.budget_kzt, 1000000)
        self.assertEqual(state.pending.event_date, "2026-11-14")
        self.assertIsNone(state.last_result)
        confirm_search(state, [BASE], backend)
        self.assertEqual(state.last_result["status"], "SUCCESS")
        send("а подешевле?", ambiguities=[Ambiguity(field="budget_kzt", question="До какой суммы ищем?")])
        self.assertIsNone(state.pending)
        send("до 500 тысяч", [("budget_kzt", 500000, "500 тысяч")])
        send("перенесём на 15 ноября 2026", [("event_date", "2026-11-15", "15 ноября 2026")])
        self.assertEqual(state.pending.budget_kzt, 500000)
        self.assertEqual(state.pending.event_date, "2026-11-15")
        confirm_search(state, [BASE], backend)
        self.assertEqual(state.last_result["status"], "NO_MATCH")
        self.assertEqual(state.last_result["rejections"], {"budget": 1})

    def test_chat_renders_optional_wording_from_separate_map(self):
        request = next(iter(DEMOS.values()))
        backend = Mock()
        backend.parse.return_value = decision(updates=[
            Update(field=k, value=v, evidence="2026") for k, v in asdict(request).items()
        ])
        backend.explain.side_effect = lambda request, result: {
            c["contractor"].id: "Проверенное объяснение для этой карточки." for c in result["cards"]
        }
        with patch("eventmatch.infrastructure.openai_client.OpenAIBackend", return_value=backend):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
            app.chat_input[0].set_value("Мероприятие 2026").run()
            app.button(key="confirm_chat").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.subheader), 3)
            self.assertEqual(sum("Проверенное объяснение для этой карточки" in m.value for m in app.markdown), 3)
            self.assertEqual(app.session_state.conversation.last_result, recommend(load_catalog(DEFAULT_CATALOG), request))


if __name__ == "__main__":
    unittest.main()

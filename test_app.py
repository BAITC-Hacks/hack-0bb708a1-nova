"""UI smoke tests use Streamlit's bundled test runner; no browser needed."""
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from demo import DEMOS


class AppTests(unittest.TestCase):
    def test_all_demo_outcomes_and_input_changes(self):
        app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=20).run()
        self.assertFalse(app.exception)
        for index, title in enumerate(DEMOS):
            app.selectbox(key="demo_choice").select(title).run()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.subheader), [3, 1, 0, 0][index])
            if index == 1:
                self.assertTrue(any("Синтетический профиль" in c.value for c in app.caption))
            if index >= 2:
                self.assertEqual(len(app.warning), 1)
        app.selectbox(key="demo_choice").select(next(iter(DEMOS))).run()
        app.button[0].click().run()
        self.assertEqual(len(app.subheader), 3)
        app.number_input(key="budget").set_value(1).run()
        self.assertEqual(len(app.subheader), 0)
        app.button[0].click().run()
        self.assertEqual(len(app.warning), 1)


if __name__ == "__main__":
    unittest.main()

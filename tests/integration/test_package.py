"""Installed-package paths and command-line entry points; no network calls."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eventmatch.infrastructure.openai_client import configuration
from eventmatch.paths import DEFAULT_CATALOG, ENV_FILE
from tests.support import ROOT


class PackageTests(unittest.TestCase):
    def test_default_catalog_is_independent_of_working_directory(self):
        env = dict(os.environ)
        env.pop("NOVA_DATASET", None)
        env.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run([sys.executable, "-c", """
from eventmatch.paths import CATALOG_PATH
from eventmatch.domain.matcher import load_catalog
assert len(load_catalog(CATALOG_PATH)) == 66
"""], cwd=directory, env=env, check=True, capture_output=True)

    def test_dataset_override_preserves_absolute_and_relative_paths(self):
        for value in (str(DEFAULT_CATALOG), str(DEFAULT_CATALOG.relative_to(ROOT))):
            env = dict(os.environ, NOVA_DATASET=value)
            subprocess.run([sys.executable, "-c", """
import os
from pathlib import Path
from eventmatch.paths import CATALOG_PATH
from eventmatch.domain.matcher import load_catalog
assert CATALOG_PATH == Path(os.environ['NOVA_DATASET'])
assert len(load_catalog(CATALOG_PATH)) == 66
"""], cwd=ROOT, env=env, check=True, capture_output=True)

    def test_dotenv_uses_checkout_root_and_keeps_environment_priority(self):
        self.assertEqual(ENV_FILE, ROOT / ".env")
        with patch("eventmatch.infrastructure.openai_client.load_dotenv") as load, \
                patch.dict(os.environ, OPENAI_API_KEY="test-placeholder", OPENAI_MODEL="test-model"):
            self.assertEqual(configuration(), ("test-placeholder", "test-model"))
        load.assert_called_once_with(ENV_FILE, override=False)

    def test_scripts_can_be_invoked_without_pythonpath(self):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.pop("NOVA_DATASET", None)
        help_result = subprocess.run(
            [sys.executable, "scripts/eval_live.py", "--help"],
            cwd=ROOT, env=env, check=True, capture_output=True, text=True,
        )
        self.assertIn("--suite", help_result.stdout)
        demos = subprocess.run(
            [sys.executable, "scripts/demo.py"],
            cwd=ROOT, env=env, check=True, capture_output=True, text=True,
        )
        self.assertEqual(demos.stdout.count("SUCCESS:"), 2)
        self.assertIn("CATEGORY_NOT_FOUND:", demos.stdout)
        self.assertIn("NO_MATCH:", demos.stdout)

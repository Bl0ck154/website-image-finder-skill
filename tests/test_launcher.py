"""Launcher tests use mocks and never install packages or access the network."""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import skill


class LauncherTests(unittest.TestCase):
    def test_setup_uses_isolated_environment_when_required(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            env = root / "env"
            fake_python = env / "bin" / "python"
            with mock.patch.object(skill, "environment_locations", return_value=[env]), \
                 mock.patch.object(skill, "python_works", return_value=False), \
                 mock.patch.object(skill, "current_python_ready", return_value=False), \
                 mock.patch.object(skill, "install_isolated", return_value=fake_python) as installer:
                self.assertEqual(skill.prepared_python(["search"], allow_install=True), fake_python)
                installer.assert_called_once_with(env)

    def test_opt_out_does_not_install(self):
        with tempfile.TemporaryDirectory() as path:
            with mock.patch.object(skill, "environment_locations", return_value=[Path(path) / "venv"]), \
                 mock.patch.object(skill, "python_works", return_value=False), \
                 mock.patch.object(skill, "current_python_ready", return_value=False), \
                 mock.patch.object(skill, "install_isolated") as installer:
                self.assertIsNone(skill.prepared_python(["search"], allow_install=False))
                installer.assert_not_called()

    def test_ready_environment_is_reused(self):
        with tempfile.TemporaryDirectory() as path:
            executable = skill.managed_python(Path(path) / "venv")
            with mock.patch.object(skill, "environment_locations", return_value=[Path(path) / "venv"]), \
                 mock.patch.object(skill, "python_works", return_value=True), \
                 mock.patch.object(skill, "install_isolated") as installer:
                self.assertEqual(skill.prepared_python(["search"], allow_install=True), executable)
                installer.assert_not_called()

    def test_help_is_read_only(self):
        with mock.patch.object(sys, "argv", ["skill.py", "search", "--help"]), \
             mock.patch.object(skill, "prepared_python") as setup, \
             mock.patch.object(skill.subprocess, "run") as run:
            run.return_value.returncode = 0
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(skill.main(), 0)
            setup.assert_not_called()

    def test_project_root_detection(self):
        with tempfile.TemporaryDirectory() as path:
            self.assertEqual(skill.project_root(["search", "--root", path]), Path(path).resolve())
            self.assertEqual(skill.project_root(["search", "--root=" + path]), Path(path).resolve())

    def test_cli_no_auto_setup_override(self):
        with mock.patch.dict(os.environ, {"WEBSITE_IMAGE_FINDER_AUTO_SETUP": "0"}), \
             mock.patch.object(sys, "argv", ["skill.py", "search", "lake"]), \
             mock.patch.object(skill, "prepared_python", return_value=None) as setup, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(skill.main(), 2)
            self.assertFalse(setup.call_args.kwargs["allow_install"])


if __name__ == "__main__":
    unittest.main()

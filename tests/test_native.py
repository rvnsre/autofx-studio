"""Adapter contracts against mocks; these do not certify an installed NLE."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from autofx.media import FXError, temporary_directory
from autofx.native import aerender, after_effects, resolve_import


class NativeContractTests(unittest.TestCase):
    def setUp(self):
        context = temporary_directory()
        self.root = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.xml = self.root / "timeline.xml"
        self.xml.write_text("<xmeml/>")

    def test_resolve_creates_separate_project_and_checks_completion(self):
        project = MagicMock()
        project.GetRenderJobStatus.return_value = {"JobStatus": "Complete"}
        project.IsRenderingInProgress.return_value = False
        resolve = MagicMock()
        manager = resolve.GetProjectManager.return_value
        manager.CreateProject.return_value = project
        module = SimpleNamespace(scriptapp=lambda name: resolve)
        with patch("autofx.native.importlib.import_module", return_value=module):
            name = resolve_import(self.xml, render_dir=self.root / "native",
                                  render_preset="Installed preset")
        self.assertTrue(name.startswith("AutoFX_"))
        manager.CreateProject.assert_called_once_with(name)
        manager.SaveProject.assert_called_once()
        project.LoadRenderPreset.assert_called_once_with("Installed preset")
        project.StartRendering.assert_called_once()

    def test_resolve_refuses_missing_preset_before_connecting(self):
        with self.assertRaises(FXError):
            resolve_import(self.xml, render_dir=self.root / "render")

    def test_resolve_reports_failed_import(self):
        resolve = MagicMock()
        manager = resolve.GetProjectManager.return_value
        manager.CreateProject.return_value.GetMediaPool.return_value.ImportTimelineFromFile.return_value = None
        with patch("autofx.native.importlib.import_module",
                   return_value=SimpleNamespace(scriptapp=lambda name: resolve)):
            with self.assertRaises(FXError):
                resolve_import(self.xml)
        manager.SaveProject.assert_not_called()

    def test_native_timeout_validation(self):
        with self.assertRaises(FXError):
            after_effects(self.xml, self.xml, timeout=-1)
        with self.assertRaises(FXError):
            aerender(self.xml, self.xml, self.root / "out.mov", "Lossless", timeout=0)


if __name__ == "__main__":
    unittest.main()

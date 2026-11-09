"""Verify persistent backups and restoration without changing Windows settings."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch


class FpsTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(sys.modules, {"webview": types.ModuleType("webview"), "psutil": MagicMock()}):
            spec = importlib.util.spec_from_file_location("fps_test_app", Path(__file__).parents[1] / "app.py")
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        self.module.winreg = None
        self.api = self.module.Api()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.api._fps_backup_path = lambda: str(Path(self.directory.name) / "backup.json")

    def test_backup_precedes_change_and_survives_failed_apply(self):
        service = self.module.psutil.win_service_get.return_value
        service.start_type.return_value = "manual"
        service.status.return_value = "stopped"
        def apply(name, enabled):
            self.assertEqual(self.api._fps_backups()[name], {"start": "demand", "running": False})
            return False
        self.api.set_service = MagicMock(side_effect=apply)
        result = self.api.fps_set("DiagTrack", True)
        self.assertFalse(result["ok"])
        self.assertIn("DiagTrack", self.api._fps_backups())

    def test_restore_original_service_not_default(self):
        self.api._fps_save({"DiagTrack": {"start": "demand", "running": False}})
        self.module.psutil.win_service_get.return_value.status.return_value = "running"
        self.module.run = MagicMock(return_value=(0, ""))
        self.assertTrue(self.api.fps_set("DiagTrack", False)["ok"])
        self.assertEqual(self.module.run.call_args_list[0].args[0], ["sc", "config", "DiagTrack", "start=", "demand"])
        self.assertEqual(self.module.run.call_args_list[1].args[0], ["sc", "stop", "DiagTrack"])
        self.assertEqual(self.api._fps_backups(), {})

    def test_restore_failure_keeps_backup(self):
        self.api._fps_save({"DiagTrack": {"start": "auto", "running": True}})
        self.module.run = MagicMock(return_value=(1, "denied"))
        self.assertFalse(self.api.fps_set("DiagTrack", False)["ok"])
        self.assertIn("DiagTrack", self.api._fps_backups())

    def test_corrupt_backup_blocks_changes(self):
        Path(self.api._fps_backup_path()).write_text("not json")
        self.api.setplan = MagicMock()
        self.assertFalse(self.api.fps_set("energy", True)["ok"])
        self.api.setplan.assert_not_called()

    def test_energy_restores_exact_previous_plan_after_reopen(self):
        original = "a1841308-3541-4fab-bc81-f71556f20b4a"
        self.api.plans = lambda: [{"id": original, "on": True, "name": "Custom"}]
        self.api.setplan = MagicMock(return_value=True)
        self.assertTrue(self.api.fps_set("energy", True)["ok"])
        reopened = self.module.Api()
        reopened._fps_backup_path = self.api._fps_backup_path
        reopened.setplan = MagicMock(return_value=True)
        self.assertTrue(reopened.fps_set("energy", False)["ok"])
        reopened.setplan.assert_called_once_with(original)

    def test_invalid_nested_backup_blocks_changes(self):
        Path(self.api._fps_backup_path()).write_text(json.dumps({"DiagTrack": "invalid"}))
        self.api.set_service = MagicMock()
        self.assertFalse(self.api.fps_set("DiagTrack", True)["ok"])
        self.api.set_service.assert_not_called()

    def test_unknown_and_unsafe_services_cannot_be_applied(self):
        self.api.set_service = MagicMock()
        for key in ["Unknown", "Spooler", "SysMain"]:
            self.assertFalse(self.api.fps_set(key, True)["ok"])
        self.api.set_service.assert_not_called()


if __name__ == "__main__":
    unittest.main()

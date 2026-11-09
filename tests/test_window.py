"""Window bridge tests: no changes to the host PC or GUI startup."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.webview = types.ModuleType("webview")
        self.webview.create_window = MagicMock()
        self.webview.start = MagicMock()
        with patch.dict(sys.modules, {"webview": self.webview, "psutil": MagicMock()}):
            spec = importlib.util.spec_from_file_location("panel_test", Path(__file__).parents[1] / "app.py")
            self.app = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.app)
        self.api = self.app.Api()
        self.window = MagicMock()
        self.api._window = self.window

    def test_actions_and_event_synchronization(self):
        self.assertFalse(self.api.window_action("arbitrary_command"))
        self.window.assert_not_called()
        self.assertTrue(self.api.window_action("maximize"))
        self.window.maximize.assert_called_once()
        self.api._set_maximized(True)
        self.assertEqual(self.api.window_state(), {"maximized": True})
        self.api.window_action("maximize")
        self.window.restore.assert_called_once()
        self.api._set_maximized(False)
        self.assertFalse(self.api.window_state()["maximized"])
        self.api.window_action("minimize")
        self.window.minimize.assert_called_once()
        self.api.window_action("close")
        self.window.destroy.assert_called_once()

    def test_no_window(self):
        self.api._window = None
        self.assertFalse(self.api.window_action("close"))

    def test_frameless_window_configuration(self):
        with patch.object(self.app.threading, "Thread"):
            self.app.main()
        kwargs = self.webview.create_window.call_args.kwargs
        self.assertTrue(kwargs["frameless"])
        self.assertFalse(kwargs["easy_drag"])
        self.assertTrue(kwargs["resizable"])
        self.assertEqual(kwargs["min_size"], (1000, 700))
        self.webview.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()

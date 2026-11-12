"""Window bridge tests: no changes to the host PC or GUI startup."""
import importlib.util
import tempfile
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

    def test_privacy_allowlist(self):
        self.assertEqual(set(self.api._PRIVACY_ITEMS), {"search_web", "feedback", "search_history"})
        self.assertFalse(self.api.privacy_apply("disable_defender")["ok"])
        self.assertFalse(self.api.privacy_restore("diagtrack")["ok"])

    def test_game_boost_allowlist_and_file_backup_restore(self):
        self.assertEqual(set(self.api._GB_IDS),
                         {"valorant", "minecraft", "fortnite", "bluestacks", "discord"})
        self.assertFalse(self.api.game_optimize("unknown")["ok"])
        self.assertFalse(self.api.game_restore("unknown")["ok"])
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "options.txt"
            original = b"renderDistance:16\nsimulationDistance:12\notherSetting:keep\n"
            config.write_bytes(original)
            with patch.object(self.api, "_gb_path_for", return_value=str(config)), \
                 patch.object(self.api, "_gb_root", return_value=folder), \
                 patch.object(self.api, "_gb_running", return_value=False):
                result = self.api.game_optimize("minecraft")
                self.assertTrue(result["ok"], result)
                updated = config.read_text()
                self.assertIn("renderDistance:8", updated)
                self.assertIn("otherSetting:keep", updated)
                self.assertTrue(self.api.game_profiles()["minecraft"]["applied"])
                self.assertFalse(self.api.game_optimize("minecraft")["ok"])
                restored = self.api.game_restore("minecraft")
                self.assertTrue(restored["ok"], restored)
                self.assertEqual(config.read_bytes(), original)

    def test_discord_community_opens_only_official_invite(self):
        with patch.object(self.app.webbrowser, "open", return_value=True) as opener:
            self.assertTrue(self.api.open_community())
            opener.assert_called_once_with("https://discord.gg/efdF2Cfrb", new=2)

    def test_input_lag_allowlist_and_restore(self):
        self.assertEqual(set(self.api._INPUT_ITEMS),
                         {"mouse_acceleration", "background_capture"})
        self.assertFalse(self.api.input_lag_apply("disable_defender")["ok"])
        self.assertFalse(self.api.input_lag_restore("remove_update")["ok"])
        entries = self.api._INPUT_ITEMS["mouse_acceleration"]
        live = {(e[0], e[1]): {"exists": True, "value": "1", "type": 1}
                for group in self.api._INPUT_ITEMS.values() for e in group}
        def read(entry):
            return dict(live[(entry[0], entry[1])])
        def write(entry, state):
            live[(entry[0], entry[1])] = dict(state)
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(self.app.os, "name", "nt"), \
             patch.object(self.app, "winreg", MagicMock()), \
             patch.object(self.api, "_input_backup_path", return_value=str(Path(folder)/"backup.json")), \
             patch.object(self.api, "_input_read", side_effect=read), \
             patch.object(self.api, "_input_write", side_effect=write):
            applied = self.api.input_lag_apply("mouse_acceleration")
            self.assertTrue(applied["ok"], applied)
            self.assertTrue(self.api.input_lag_status()["mouse_acceleration"]["applied"])
            self.assertTrue(self.api.input_lag_status()["mouse_acceleration"]["restorable"])
            restored = self.api.input_lag_restore("mouse_acceleration")
            self.assertTrue(restored["ok"], restored)
            self.assertTrue(all(item["value"] == "1" for item in live.values()))
            self.assertFalse(self.api.input_lag_status()["mouse_acceleration"]["restorable"])

    def test_driver_pages_are_official(self):
        with patch.object(self.app.webbrowser, "open", return_value=True) as opener:
            self.assertFalse(self.api.open_driver_page("random"))
            self.assertTrue(self.api.open_driver_page("nvidia"))
            self.assertTrue(self.api.open_driver_page("amd"))
            urls = [call.args[0] for call in opener.call_args_list]
            self.assertEqual(urls, ["https://www.nvidia.com/pt-br/drivers/",
                                    "https://www.amd.com/pt/support/download/drivers.html"])

    def test_widget_allowlist_and_independent_windows(self):
        self.assertEqual(len(self.api._WIDGET_SIZES), 9)
        self.assertFalse(self.api.widget_open("command-exec")["ok"])
        self.assertFalse(self.api.widget_close("command-exec"))
        self.assertFalse(self.api.widget_update("command-exec", {"accent": "red"}))
        self.assertEqual(self.api.widget_get_config("command-exec"), {})
        self.assertEqual(self.api._widget_clean_config({"accent": "bad", "unit": "Z",
                            "on_top": "yes", "note": "a" * 500})["accent"], "blue")
        self.assertEqual(len(self.api._widget_clean_config({"note": "b" * 500})["note"]), 400)
        child = MagicMock()
        with patch.object(self.app.webview, "create_window", return_value=child) as creator:
            result = self.api.widget_open("pixel-clock", {"accent": "violet", "on_top": True})
            self.assertTrue(result["ok"])
            self.assertEqual(self.api.widget_list(), ["pixel-clock"])
            kwargs = creator.call_args.kwargs
            self.assertTrue(kwargs["frameless"])
            self.assertTrue(kwargs["transparent"])
            self.assertTrue(kwargs["on_top"])
            self.assertFalse(kwargs["resizable"])
            self.assertIn("assets/widgets/widget_desktop.html", creator.call_args.args[1])
            self.assertIn("#pixel-clock", creator.call_args.args[1])
            self.assertTrue(self.api.widget_open("pixel-clock")["already"])
            self.assertEqual(creator.call_count, 1)
            self.assertTrue(self.api.widget_update("pixel-clock", {"accent": "mint"}))
            self.assertTrue(self.api.widget_close("pixel-clock"))
            child.destroy.assert_called_once()
            self.assertEqual(self.api.widget_list(), [])

    def test_widget_weather_requires_city_without_network(self):
        self.assertFalse(self.api.weather_for_city("")["ok"])
        self.assertFalse(self.api.weather_for_city("a")["ok"])
        with patch.object(self.app.urllib.request, "urlopen", side_effect=OSError("offline")):
            out = self.api.weather_for_city("Minha Cidade")
            self.assertFalse(out["ok"])
            self.assertIn("internet", out["error"])

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

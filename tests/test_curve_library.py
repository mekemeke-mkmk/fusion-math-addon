"""Tests for saving/loading the function library and the preset gallery."""

import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))

import curve_engine  # noqa: E402
import curve_library  # noqa: E402


class LibraryFileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = str(pathlib.Path(self.folder.name) / "sub" / "library.json")

    def tearDown(self):
        self.folder.cleanup()

    def test_round_trip_keeps_definitions(self):
        curves = [
            {"name": "Wave", "type": "implicit", "expr": "a*sin(x)", "step": 0.1,
             "variables": {"a": 2.0}, "variables_text": "a=2", "enabled": True},
            {"name": "Coil", "type": "parametric3d", "x_expr": "cos(t)", "y_expr": "sin(t)",
             "z_expr": "t", "t_start": 0, "t_end": 6, "t_step": 0.1, "close_mode": "line"},
        ]
        curve_library.save_library(self.path, curves)
        loaded, message = curve_library.load_library(self.path)

        self.assertIsNone(message)
        self.assertEqual([c["name"] for c in loaded], ["Wave", "Coil"])
        self.assertEqual(loaded[0]["variables"], {"a": 2.0})
        self.assertFalse(loaded[0]["enabled"])
        self.assertEqual(loaded[1]["z_expr"], "t")
        self.assertEqual(loaded[1]["close_mode"], "line")

    def test_missing_file_is_empty_library(self):
        self.assertEqual(curve_library.load_library(self.path), ([], None))

    def test_broken_file_is_kept_aside(self):
        pathlib.Path(self.path).parent.mkdir(parents=True)
        pathlib.Path(self.path).write_text("{not json", encoding="utf-8")
        loaded, message = curve_library.load_library(self.path)
        self.assertEqual(loaded, [])
        self.assertIn(".broken", message)
        self.assertTrue(pathlib.Path(self.path + ".broken").exists())

    def test_invalid_entries_are_skipped(self):
        payload = {"curves": [{"type": "unknown"}, {"name": "Ok", "type": "implicit", "expr": "x"}]}
        curves, skipped = curve_library.parse_library(payload)
        self.assertEqual(([c["name"] for c in curves], skipped), (["Ok"], 1))

    def test_non_library_json_is_rejected(self):
        with self.assertRaises(ValueError):
            curve_library.parse_library({"hello": 1})

    def test_merge_renames_duplicates(self):
        existing = [{"name": "Wave"}]
        curve_library.merge_curves(existing, [{"name": "Wave"}, {"name": "Wave"}])
        self.assertEqual([c["name"] for c in existing], ["Wave", "Wave (2)", "Wave (3)"])

    def test_saved_file_is_utf8_json(self):
        curve_library.save_library(self.path, [{"name": "波", "type": "implicit", "expr": "x"}])
        data = json.loads(pathlib.Path(self.path).read_text(encoding="utf-8"))
        self.assertEqual(data["format"], curve_library.LIBRARY_FORMAT)
        self.assertEqual(data["curves"][0]["name"], "波")


class PresetTests(unittest.TestCase):
    def test_every_preset_draws_without_problems(self):
        for preset in curve_library.PRESETS:
            curve = curve_library.curve_from_preset(preset)
            result = curve_engine.sample_curve(curve, {}, (0, 10), max_abs_value=1.0e5)
            self.assertEqual((result.errors, result.warnings), ([], []), preset["name"])
            self.assertEqual(len(result.pieces), 1, preset["name"])

    def test_preset_variables_are_editable_text(self):
        curve = curve_library.curve_from_preset(curve_library.PRESETS[0])
        self.assertEqual(curve["variables_text"], "A=1,L=10")


if __name__ == "__main__":
    unittest.main()

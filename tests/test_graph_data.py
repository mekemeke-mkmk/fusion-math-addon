"""Tests for the graph window's sampling and edit handling."""

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))

import graph_data  # noqa: E402

VIEW = {"xmin": -5, "xmax": 5, "ymin": -3, "ymax": 3}


def implicit(expr, variables=None):
    variables = variables or {}
    return {"name": "f", "type": "implicit", "expr": expr, "step": 0.2, "variables": dict(variables),
            "variables_text": ",".join(f"{k}={v}" for k, v in variables.items())}


def circle():
    return {"name": "c", "type": "parametric", "x_expr": "r*cos(t)", "y_expr": "r*sin(t)",
            "t_start": 0.0, "t_end": 6.283185307179586, "t_step": 0.5, "variables": {"r": 2.0},
            "close_mode": "smooth"}


def new_curve():
    return implicit("x")


class PayloadTests(unittest.TestCase):
    def test_implicit_curve_uses_real_x_over_the_view(self):
        payload = graph_data.graph_payload([implicit("2*x")], {}, VIEW)
        piece = payload["curves"][0]["pieces"][0]
        self.assertEqual(piece[0], [-5.0, -10.0])
        self.assertEqual(piece[-1], [5.0, 10.0])
        self.assertGreaterEqual(len(piece), graph_data.SAMPLES_PER_VIEW)

    def test_parametric_curve_is_sampled_finely_regardless_of_its_step(self):
        payload = graph_data.graph_payload([circle()], {}, VIEW)
        curve = payload["curves"][0]
        self.assertGreaterEqual(len(curve["pieces"][0]), graph_data.SAMPLES_PER_PARAMETRIC)
        self.assertTrue(curve["closed"])

    def test_poles_are_split_and_reported(self):
        curve = graph_data.graph_payload([implicit("tan(x)")], {}, VIEW)["curves"][0]
        self.assertGreater(len(curve["pieces"]), 1)
        self.assertTrue(curve["warnings"])

    def test_errors_are_returned_for_broken_expressions(self):
        curve = graph_data.graph_payload([implicit("sin(x")], {}, VIEW)["curves"][0]
        self.assertEqual(curve["pieces"], [])
        self.assertIn("Syntax error", curve["errors"][0])

    def test_hidden_curves_are_not_sampled(self):
        payload = graph_data.graph_payload([implicit("x"), implicit("x")], {}, VIEW, hidden=[1])
        self.assertTrue(payload["curves"][0]["pieces"])
        self.assertEqual(payload["curves"][1]["pieces"], [])

    def test_bad_view_falls_back_to_default(self):
        payload = graph_data.graph_payload([implicit("x")], {}, {"xmin": 1, "xmax": 1, "ymin": "a"})
        self.assertEqual(payload["view"]["xmin"], -10.0)

    def test_payload_is_json(self):
        json.dumps(graph_data.graph_payload([implicit("x"), circle()], {}, VIEW))


class EditTests(unittest.TestCase):
    def test_expression_and_variable_edits(self):
        curve = implicit("a*x", {"a": 1.0})
        self.assertTrue(graph_data.apply_edit(curve, {"expr": "a*x^2", "variables": {"a": 3}}))
        self.assertEqual((curve["expr"], curve["variables"], curve["variables_text"]),
                         ("a*x^2", {"a": 3.0}, "a=3"))

    def test_unknown_or_wrong_type_fields_are_ignored(self):
        curve = implicit("x")
        self.assertFalse(graph_data.apply_edit(curve, {"x_expr": "t", "t_start": 2, "step": 9,
                                                       "variables": {"new": 1}, "name": "  "}))
        self.assertNotIn("x_expr", curve)
        self.assertEqual(curve["variables"], {})

    def test_parametric_range_edit_rejects_non_finite_numbers(self):
        curve = circle()
        graph_data.apply_edit(curve, {"t_end": "nan", "t_start": 1})
        self.assertEqual((curve["t_start"], curve["t_end"]), (1.0, 6.283185307179586))


class RequestTests(unittest.TestCase):
    def test_preview_edit_is_not_saved_but_commit_is(self):
        curves = [implicit("a*x", {"a": 1.0})]
        _, saved = graph_data.handle_request("graphEdit", {"index": 0, "changes": {"variables": {"a": 2}},
                                                           "commit": False, "view": VIEW}, curves, {}, new_curve)
        self.assertFalse(saved)
        self.assertEqual(curves[0]["variables"]["a"], 2.0)
        _, saved = graph_data.handle_request("graphEdit", {"index": 0, "changes": {}, "commit": True},
                                             curves, {}, new_curve)
        self.assertTrue(saved)

    def test_add_selects_the_new_curve(self):
        curves = [implicit("x")]
        reply, saved = graph_data.handle_request("graphAdd", {"view": VIEW}, curves, {}, new_curve)
        self.assertTrue(saved)
        self.assertEqual((len(curves), reply["select"]), (2, 1))

    def test_invalid_requests_return_errors(self):
        reply, _ = graph_data.handle_request("graphEdit", {"index": 5, "changes": {}}, [], {}, new_curve)
        self.assertIn("error", reply)
        reply, _ = graph_data.handle_request("deleteEverything", {}, [], {}, new_curve)
        self.assertIn("error", reply)


if __name__ == "__main__":
    unittest.main()

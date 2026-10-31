"""Tests for expression checking, discontinuity detection, and load limits."""

import math
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))

import curve_engine  # noqa: E402


def implicit(expr, step=0.2, variables=None):
    return {"name": "f", "type": "implicit", "expr": expr, "step": step, "variables": variables or {}}


def parametric(x_expr, y_expr, t_end=2 * math.pi, t_step=0.1, z_expr=None, close_mode="open"):
    curve = {"name": "p", "type": "parametric", "x_expr": x_expr, "y_expr": y_expr,
             "t_start": 0.0, "t_end": t_end, "t_step": t_step, "variables": {}, "close_mode": close_mode}
    if z_expr is not None:
        curve["type"] = "parametric3d"
        curve["z_expr"] = z_expr
    return curve


def sample(curve, x_range=(0, 10)):
    return curve_engine.sample_curve(curve, {}, x_range, max_abs_value=1.0e5)


class ExpressionCheckTests(unittest.TestCase):
    def test_syntax_error_is_reported(self):
        self.assertIn("Syntax error", curve_engine.check_curve(implicit("sin(x"))[0])

    def test_unknown_name_suggests_variable(self):
        problems = curve_engine.check_curve(implicit("a*x"))
        self.assertIn("Unknown name 'a'", problems[0])
        self.assertEqual(curve_engine.check_curve(implicit("a*x", variables={"a": 1})), [])

    def test_user_parameters_are_known_names(self):
        self.assertEqual(curve_engine.check_curve(implicit("width*x"), ["width"]), [])

    def test_unsafe_constructs_are_rejected(self):
        for expr in ("__import__('os')", "x.real", "[x]", "lambda: 1", "'a'"):
            self.assertTrue(curve_engine.check_curve(implicit(expr)), expr)

    def test_caret_means_power(self):
        result = sample(implicit("x^2", step=1.0))
        self.assertEqual(result.pieces[0][3][1], 9.0)

    def test_non_positive_step_is_an_error(self):
        self.assertTrue(curve_engine.check_curve(implicit("x", step=0)))

    def test_huge_integer_power_does_not_hang(self):
        result = sample(implicit("9**9**9"))
        self.assertTrue(result.errors)

    def test_wrong_argument_count_is_an_error(self):
        result = sample(implicit("sin(x, 2)"))
        self.assertIn("Invalid function call", result.errors[0])


class SamplingTests(unittest.TestCase):
    def test_smooth_function_is_one_piece_without_warnings(self):
        for expr in ("sin(x)", "exp(x)", "x**3", "atan(100*(x-5))"):
            result = sample(implicit(expr))
            self.assertEqual((len(result.pieces), result.warnings, result.errors), (1, [], []), expr)

    def test_range_end_is_always_sampled(self):
        result = sample(implicit("x", step=0.3), (0, 1))
        self.assertAlmostEqual(result.pieces[0][-1][0], 1.0)

    def test_implicit_points_start_at_range_origin(self):
        result = sample(implicit("x", step=1.0), (2, 4))
        self.assertEqual(result.pieces[0][0], (0.0, 2.0, 0.0))

    def test_tan_poles_split_the_curve(self):
        result = sample(implicit("tan(x)"), (0, 20))
        self.assertEqual(len(result.pieces), 7)
        self.assertIn("Discontinuity", result.warnings[0])
        self.assertIn("1.57", result.warnings[0])

    def test_steps_split_the_curve(self):
        result = sample(implicit("floor(x)"), (0, 3.5))
        self.assertEqual(len(result.pieces), 4)

    def test_pole_at_zero_is_reported_at_zero(self):
        result = sample(implicit("1/x", step=0.3), (-5, 5))
        self.assertEqual(len(result.pieces), 2)
        self.assertIn("x≈0", result.warnings[0])

    def test_undefined_region_is_a_gap_warning(self):
        result = sample(implicit("sqrt(x)"), (-5, 5))
        self.assertEqual(len(result.pieces), 1)
        self.assertIn("undefined", result.warnings[0])

    def test_too_many_points_stops_before_evaluating(self):
        result = sample(implicit("x", step=0.0001), (0, 100))
        self.assertIn("Too many sample points", result.errors[0])

    def test_time_budget_stops_calculation(self):
        ticks = iter(range(10 ** 6))
        result = curve_engine.sample_curve(implicit("x"), {}, (0, 10), clock=lambda: next(ticks),
                                           limits={"time_budget_seconds": 5})
        self.assertIn("longer than", result.errors[0])

    def test_parametric_and_3d_curves(self):
        circle = sample(parametric("cos(t)", "sin(t)"))
        self.assertEqual(len(circle.pieces), 1)
        self.assertTrue(curve_engine.endpoints_coincide(circle.pieces[0], 1.0e-9))

        helix = sample(parametric("cos(t)", "sin(t)", z_expr="t"))
        self.assertAlmostEqual(helix.pieces[0][-1][2], 2 * math.pi)

    def test_closing_a_curve_with_gaps_warns(self):
        result = sample(parametric("t", "tan(t)", t_end=3.0, t_step=0.1, close_mode="smooth"))
        self.assertTrue(any("will not be connected" in w for w in result.warnings))


class PointHelperTests(unittest.TestCase):
    def test_remove_duplicate_points(self):
        points = [(0, 0, 0), (0, 0, 0), (1, 0, 0)]
        self.assertEqual(curve_engine.remove_duplicate_points(points, 1.0e-9), [(0, 0, 0), (1, 0, 0)])


if __name__ == "__main__":
    unittest.main()

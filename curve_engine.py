"""Expression checking and curve sampling for Math Curve.

This module has no Fusion dependency so it can be unit-tested outside Fusion.
All coordinates returned here are in "function units" (the unit selected in
the Setup tab); math_curve_2.py scales them to Fusion's internal centimeters.
"""

import ast
import math
import time


FUNCTIONS = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "asinh": math.asinh,
    "acosh": math.acosh,
    "atanh": math.atanh,
    "exp": math.exp,
    "sqrt": math.sqrt,
    "cbrt": lambda v: math.copysign(abs(v) ** (1.0 / 3.0), v),
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "abs": abs,
    "fabs": math.fabs,
    "floor": math.floor,
    "ceil": math.ceil,
    "round": round,
    "pow": math.pow,
    "hypot": math.hypot,
    "min": min,
    "max": max,
    "sign": lambda v: (v > 0) - (v < 0),
    "radians": math.radians,
    "degrees": math.degrees,
}

CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}

RESERVED_NAMES = set(FUNCTIONS) | set(CONSTANTS) | {"x", "t"}

_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Call, ast.Name, ast.Load, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
)

# Evaluation problems that mean "the curve is undefined here", not "the expression is wrong".
UNDEFINED_ERRORS = (ZeroDivisionError, ValueError, OverflowError)

LIMITS = {
    # Hard limits stop the curve. Soft limits require "Draw anyway".
    "max_points_per_curve": 20000,
    "warn_points_total": 4000,
    "max_pieces_per_curve": 200,
    "warn_pieces_per_curve": 20,
    "time_budget_seconds": 3.0,
    # Larger coordinates are treated as undefined (in centimeters, 1 km).
    "max_abs_value_cm": 1.0e5,
}

CLOSE_OPEN = "open"
CLOSE_SMOOTH = "smooth"
CLOSE_LINE = "line"
CLOSE_MODES = (CLOSE_OPEN, CLOSE_SMOOTH, CLOSE_LINE)

CURVE_TYPES = ("implicit", "parametric", "parametric3d")

_JUMP_RATIO = 2.5
_BISECT_STEPS = 24
_REFINE_POINTS = 8


class ExpressionError(ValueError):
    """Raised when an expression cannot be used, with a user-facing message."""


class _FloatConstants(ast.NodeTransformer):
    # Integer powers like 9**9**9 never finish in Python; floats overflow quickly instead.
    def visit_Constant(self, node):
        if isinstance(node.value, int) and not isinstance(node.value, bool):
            return ast.copy_location(ast.Constant(float(node.value)), node)
        return node


def compile_expression(text, known_names):
    """Validate and compile one expression. Raises ExpressionError with a readable message."""
    source = (text or "").strip()
    if not source:
        raise ExpressionError("Expression is empty.")
    source = source.replace("^", "**")

    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as ex:
        column = (ex.offset or 0)
        raise ExpressionError(f"Syntax error near column {column}: '{source}'.") from None

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ExpressionError(f"'{type(node).__name__}' is not allowed in expressions.")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ExpressionError("Only numbers are allowed as constants.")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
                name = node.func.id if isinstance(node.func, ast.Name) else "?"
                raise ExpressionError(f"Unknown function '{name}'.")
            if node.keywords:
                raise ExpressionError(f"'{node.func.id}' does not accept keyword arguments.")
        if isinstance(node, ast.Name) and not (isinstance(node.ctx, ast.Load)):
            raise ExpressionError("Assignments are not allowed.")
        if isinstance(node, ast.Name) and node.id not in FUNCTIONS and node.id not in CONSTANTS:
            if node.id not in known_names:
                raise ExpressionError(
                    f"Unknown name '{node.id}'. Define it in Variables (for example {node.id}=1) "
                    "or as a Fusion user parameter."
                )

    tree = ast.fix_missing_locations(_FloatConstants().visit(tree))
    return compile(tree, "<math curve>", "eval")


def evaluate(code, scope):
    """Evaluate compiled code. Returns a float, or None when undefined at this point."""
    try:
        value = eval(code, {"__builtins__": {}}, scope)
    except UNDEFINED_ERRORS:
        return None
    except TypeError as ex:
        raise ExpressionError(f"Invalid function call: {ex}") from None
    if isinstance(value, complex) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def curve_type(curve):
    value = curve.get("type", "implicit")
    return value if value in CURVE_TYPES else "implicit"


def is_parametric(curve):
    return curve_type(curve) in ("parametric", "parametric3d")


def expression_fields(curve):
    """Return [(label, field_name, independent_variable)] for the curve type."""
    kind = curve_type(curve)
    if kind == "implicit":
        return [("y", "expr", "x")]
    fields = [("x(t)", "x_expr", "t"), ("y(t)", "y_expr", "t")]
    if kind == "parametric3d":
        fields.append(("z(t)", "z_expr", "t"))
    return fields


def compile_curve(curve, param_names):
    """Compile all expressions of a curve. Returns (codes, errors)."""
    codes = []
    errors = []
    variables = set(curve.get("variables", {}).keys())
    for label, field, independent in expression_fields(curve):
        known = set(param_names) | variables | {independent}
        try:
            codes.append(compile_expression(curve.get(field, ""), known))
        except ExpressionError as ex:
            errors.append(f"{label}: {ex}")
    return codes, errors


def check_curve(curve, param_names=()):
    """Return a list of user-facing problems with the curve definition (empty when OK)."""
    _, errors = compile_curve(curve, param_names)
    if is_parametric(curve):
        step = curve.get("t_step")
        if step is None or step <= 0:
            errors.append("t Step must be greater than 0.")
    else:
        step = curve.get("step")
        if step is None or step <= 0:
            errors.append("Step must be greater than 0.")
    return errors


class CurveSamples:
    """Sampling result of one curve: drawable pieces plus problems found."""

    def __init__(self, curve):
        self.name = curve.get("name", "Curve")
        self.is_parametric = is_parametric(curve)
        self.close_mode = curve.get("close_mode", CLOSE_OPEN) if self.is_parametric else CLOSE_OPEN
        self.invert_origin = bool(curve.get("invert_origin", False))
        self.invert_x = bool(curve.get("invert_x", False))
        self.invert_y = bool(curve.get("invert_y", False))
        self.pieces = []
        self.errors = []
        self.warnings = []
        self.point_count = 0

    @property
    def drawable(self):
        return not self.errors and any(len(piece) >= 2 for piece in self.pieces)


def _sample_parameters(start, end, step):
    count = int(math.floor((end - start) / step + 1.0e-9)) + 1
    values = [start + i * step for i in range(count)]
    if end - values[-1] > step * 1.0e-6:
        values.append(end)
    return values


def _distance(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _format_positions(values, label):
    shown = ", ".join(f"{v:.3g}" for v in values[:3])
    more = "..." if len(values) > 3 else ""
    return f"{label}≈{shown}{more}"


def sample_curve(curve, params, x_range, max_abs_value=None, limits=None, clock=time.monotonic):
    """Sample a curve definition into continuous pieces.

    curve: curve dict from the library.
    params: {name: value} of Fusion user parameters (already in function units).
    x_range: (start, end) used for y = f(x) curves.
    """
    limits = dict(LIMITS, **(limits or {}))
    result = CurveSamples(curve)
    result.errors.extend(check_curve(curve, params.keys()))
    if result.errors:
        return result

    codes, _ = compile_curve(curve, params.keys())
    kind = curve_type(curve)
    scope = dict(FUNCTIONS)
    scope.update(CONSTANTS)
    scope.update(params)
    scope.update(curve.get("variables", {}))
    max_abs = max_abs_value if max_abs_value is not None else float("inf")

    if kind == "implicit":
        start, end = sorted(x_range)
        step = curve["step"]
        independent = "x"
        origin_shift = start
    else:
        start, end = sorted((curve.get("t_start", 0.0), curve.get("t_end", 2 * math.pi)))
        step = curve["t_step"]
        independent = "t"
        origin_shift = 0.0

    if end - start <= 1.0e-12:
        result.errors.append(f"The {independent} range is empty. Set different start and end values.")
        return result

    expected = int((end - start) / step) + 2
    if expected > limits["max_points_per_curve"]:
        min_step = (end - start) / limits["max_points_per_curve"]
        result.errors.append(
            f"Too many sample points ({expected}). Increase Step to at least {min_step:.4g} "
            "or shorten the range."
        )
        return result

    deadline = clock() + limits["time_budget_seconds"]
    undefined = {"count": 0}

    def point_at(value):
        scope[independent] = value
        coords = []
        for code in codes:
            coord = evaluate(code, scope)
            if coord is None or abs(coord) > max_abs:
                undefined["count"] += 1
                return None
            coords.append(coord)
        if kind == "implicit":
            return (value - origin_shift, coords[0], 0.0)
        if kind == "parametric":
            return (coords[0], coords[1], 0.0)
        return (coords[0], coords[1], coords[2])

    try:
        samples = []
        for value in _sample_parameters(start, end, step):
            samples.append((value, point_at(value)))
            if clock() > deadline:
                raise TimeoutError
        undefined_on_grid = undefined["count"]

        # Split at undefined points first.
        raw_pieces = []
        current = []
        for value, point in samples:
            if point is None:
                if current:
                    raw_pieces.append(current)
                current = []
            else:
                current.append((value, point))
        if current:
            raw_pieces.append(current)

        jumps = []
        pieces = []
        for raw in raw_pieces:
            for piece in _split_jumps(raw, point_at, jumps, deadline, clock):
                pieces.append([point for _, point in piece])
    except ExpressionError as ex:
        result.errors.append(str(ex))
        return result
    except TimeoutError:
        result.errors.append(
            f"Calculation took longer than {limits['time_budget_seconds']:.0f} s and was stopped. "
            "Increase Step or simplify the expression."
        )
        return result

    # Snap jumps found at (numerically) zero, e.g. 1/x, so the message reads x≈0.
    jumps = [0.0 if abs(j) < step * 1.0e-4 else j for j in jumps]
    result.pieces = [piece for piece in pieces if len(piece) >= 2]
    result.point_count = sum(len(piece) for piece in result.pieces)

    if not result.pieces:
        result.errors.append(
            f"No drawable points in the {independent} range. Check the range, variables, and expression."
        )
        return result

    if len(result.pieces) > limits["max_pieces_per_curve"]:
        result.errors.append(
            f"The curve breaks into {len(result.pieces)} pieces, which is too heavy to draw. "
            "Narrow the range or increase Step."
        )
        return result

    if jumps:
        result.warnings.append(
            f"Discontinuity detected ({_format_positions(jumps, independent)}). "
            f"The curve will be split into {len(result.pieces)} pieces."
        )
    if undefined_on_grid:
        result.warnings.append(
            f"{undefined_on_grid} sample point(s) are undefined or too large and are skipped, "
            "so the curve has gaps."
        )
    if len(result.pieces) > limits["warn_pieces_per_curve"]:
        result.warnings.append(f"Many pieces ({len(result.pieces)}) may make Fusion slow.")
    if result.close_mode != CLOSE_OPEN and len(result.pieces) > 1:
        result.warnings.append("The curve has gaps, so start and end will not be connected.")
    return result


def _split_jumps(raw, point_at, jumps, deadline, clock):
    """Split one run of defined samples at jumps; refine steep but continuous spots."""
    if len(raw) < 3:
        return [raw]

    distances = [_distance(raw[i][1], raw[i + 1][1]) for i in range(len(raw) - 1)]
    pieces = []
    current = [raw[0]]
    for i, d in enumerate(distances):
        neighbours = []
        if i > 0:
            neighbours.append(distances[i - 1])
        if i + 1 < len(distances):
            neighbours.append(distances[i + 1])
        # min(): a pole makes both neighbours steep, so compare with the calmer side.
        reference = min(neighbours) if neighbours else d
        a, b = raw[i], raw[i + 1]
        if d > _JUMP_RATIO * reference and d > 1.0e-9:
            if clock() > deadline:
                raise TimeoutError
            position = _find_discontinuity(a, b, point_at, d)
            if position is not None:
                jumps.append(position)
                pieces.append(current)
                current = [b]
                continue
            current.extend(_refine(a[0], b[0], point_at))
        current.append(b)
    pieces.append(current)
    return pieces


def _find_discontinuity(a, b, point_at, original):
    """Bisect towards the jump. A real jump does not shrink; returns its position or None."""
    lo, plo = a
    hi, phi = b
    for _ in range(_BISECT_STEPS):
        mid = (lo + hi) / 2.0
        pmid = point_at(mid)
        if pmid is None:
            return mid
        if _distance(plo, pmid) >= _distance(pmid, phi):
            hi, phi = mid, pmid
        else:
            lo, plo = mid, pmid
    if _distance(plo, phi) > 0.5 * original:
        return (lo + hi) / 2.0
    return None


def _refine(lo, hi, point_at):
    extra = []
    for k in range(1, _REFINE_POINTS):
        value = lo + (hi - lo) * k / _REFINE_POINTS
        point = point_at(value)
        if point is not None:
            extra.append((value, point))
    return extra


def remove_duplicate_points(points, tolerance):
    """Drop consecutive points closer than tolerance (Fusion rejects them in splines)."""
    cleaned = []
    for point in points:
        if cleaned and _distance(cleaned[-1], point) <= tolerance:
            continue
        cleaned.append(point)
    return cleaned


def endpoints_coincide(points, tolerance):
    return len(points) >= 2 and _distance(points[0], points[-1]) <= tolerance

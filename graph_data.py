"""Data for the graph window: samples curves for the visible area and applies edits.

No Fusion dependency, so it can be unit-tested outside Fusion. The palette (graph.js)
sends a view rectangle and receives curve pieces in plain graph coordinates.
"""

import math
import re

try:
    from . import curve_engine
    from . import curve_library
except ImportError:
    import curve_engine
    import curve_library


# Samples across the visible width (y = f(x)) or along the whole t range (parametric).
SAMPLES_PER_VIEW = 800
SAMPLES_PER_PARAMETRIC = 1500
GRAPH_LIMITS = {"time_budget_seconds": 0.5, "max_points_per_curve": 5000}

EDITABLE_NUMBER_FIELDS = ("t_start", "t_end")
VARIABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
CURVE_TYPE_LABELS = [
    ("implicit", "y = f(x)"),
    ("parametric", "x(t), y(t)"),
    ("parametric3d", "x(t), y(t), z(t) (beta)"),
]


def _finite(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def normalize_view(view):
    """Return (xmin, xmax, ymin, ymax) with a sane, non-empty area."""
    view = view or {}
    xmin = _finite(view.get("xmin"))
    xmax = _finite(view.get("xmax"))
    ymin = _finite(view.get("ymin"))
    ymax = _finite(view.get("ymax"))
    if None in (xmin, xmax, ymin, ymax) or xmax - xmin <= 1.0e-9 or ymax - ymin <= 1.0e-9:
        return (-10.0, 10.0, -10.0, 10.0)
    return (xmin, xmax, ymin, ymax)


def _display_curve(curve, view):
    """A copy of the curve with the step the graph needs for this view."""
    display = dict(curve)
    xmin, xmax, _, _ = view
    if curve_engine.is_parametric(curve):
        t_start = _finite(curve.get("t_start")) or 0.0
        t_end = _finite(curve.get("t_end"))
        t_end = 2 * math.pi if t_end is None else t_end
        span = abs(t_end - t_start)
        if span > 1.0e-12:
            display["t_step"] = span / SAMPLES_PER_PARAMETRIC
    else:
        display["step"] = (xmax - xmin) / SAMPLES_PER_VIEW
    return display


def default_range(value):
    """Slider range used until the user sets one: the value +/- twice its size (at least 2)."""
    span = max(abs(value), 1.0) * 2.0
    return [value - span, value + span]


def variable_ranges(curve):
    stored = curve.get("variable_ranges", {})
    ranges = {}
    for name, value in curve.get("variables", {}).items():
        pair = stored.get(name)
        ranges[name] = list(pair) if pair else default_range(value)
    return ranges


def _digits_for_view(view):
    """Decimals that keep about 1/100000 of the view size: plenty for the screen, small JSON."""
    xmin, xmax, ymin, ymax = view
    precision = max(xmax - xmin, ymax - ymin) / 1.0e5
    return max(0, min(12, -int(math.floor(math.log10(precision)))))


def curve_payload(index, curve, params, view, visible=True):
    """Everything the palette needs to show and edit one curve (points only when visible)."""
    xmin, xmax, ymin, ymax = view
    base = {
        "index": index,
        "name": curve.get("name", f"Curve {index + 1}"),
        "type": curve_engine.curve_type(curve),
        "fields": {field: curve.get(field, "") for _, field, _ in curve_engine.expression_fields(curve)},
        "t_start": curve.get("t_start"),
        "t_end": curve.get("t_end"),
        "variables": dict(curve.get("variables", {})),
        "variable_ranges": variable_ranges(curve),
        "close_mode": curve.get("close_mode", curve_engine.CLOSE_OPEN),
        "step": curve.get("step"),
        "t_step": curve.get("t_step"),
        "closed": curve.get("close_mode", curve_engine.CLOSE_OPEN) != curve_engine.CLOSE_OPEN,
        "pieces": [],
        "errors": [],
        "warnings": [],
    }
    if not visible:
        base["errors"] = curve_engine.check_curve(curve, params.keys())
        return base

    # Values far outside the view are cut, so poles end where the screen ends.
    max_abs = 50.0 * max(abs(xmin), abs(xmax), abs(ymin), abs(ymax), 1.0)
    result = curve_engine.sample_curve(
        _display_curve(curve, view), params, (xmin, xmax), max_abs_value=max_abs, limits=GRAPH_LIMITS
    )
    shift = xmin if base["type"] == "implicit" else 0.0
    digits = _digits_for_view(view)
    base["pieces"] = [
        [[round(x + shift, digits), round(y, digits)] for x, y, _ in piece] for piece in result.pieces
    ]
    base["errors"] = result.errors
    base["warnings"] = [w for w in result.warnings if not w.startswith("Many pieces")]
    return base


def graph_payload(curves, params, view, hidden=()):
    view = normalize_view(view)
    hidden = set(hidden or ())
    return {
        "view": {"xmin": view[0], "xmax": view[1], "ymin": view[2], "ymax": view[3]},
        "curves": [curve_payload(i, curve, params, view, i not in hidden) for i, curve in enumerate(curves)],
        "presets": [curve_library.preset_label(preset) for preset in curve_library.PRESETS],
        "types": [{"id": kind, "label": label} for kind, label in CURVE_TYPE_LABELS],
        "close_modes": [{"id": mode, "label": label} for mode, label in curve_library.CLOSE_MODE_LABELS],
        "params": sorted(params.keys()),
    }


def variables_text(variables):
    return ",".join(f"{name}={value:g}" for name, value in variables.items())


def check_variable_name(name, curve, params=()):
    """Return an error message for a new variable name, or None when it can be used."""
    if not isinstance(name, str) or not VARIABLE_NAME.fullmatch(name):
        return "Use letters, digits, and _ for variable names (for example a or width_2)."
    if name in curve_engine.RESERVED_NAMES:
        return f"'{name}' is a reserved name (a function, constant, x, or t)."
    if name in curve.get("variables", {}):
        return f"'{name}' already exists."
    if name in params:
        return f"'{name}' is a Fusion user parameter. Use another name, or use the parameter directly."
    return None


def _change_type(curve, kind):
    if kind not in curve_engine.CURVE_TYPES or curve_engine.curve_type(curve) == kind:
        return False
    template = curve_library.normalize_curve({"type": kind, "name": curve.get("name")})
    for key, value in template.items():
        if key not in ("name", "variables", "variables_text", "enabled") and key not in curve:
            curve[key] = value
    curve["type"] = kind
    return True


def apply_edit(curve, changes, params=()):
    """Apply an edit from the palette in place. Returns (changed, error_message_or_None).

    Only known fields are accepted; numbers must be finite.
    """
    changed = False
    error = None

    if "type" in changes:
        changed |= _change_type(curve, changes["type"])

    allowed = ["name"] + [field for _, field, _ in curve_engine.expression_fields(curve)]
    for field in allowed:
        value = changes.get(field)
        if not isinstance(value, str):
            continue
        if field == "name":
            value = value.strip()
            if not value:
                continue
        if curve.get(field) != value:
            curve[field] = value
            changed = True

    number_fields = list(EDITABLE_NUMBER_FIELDS) + ["t_step"] if curve_engine.is_parametric(curve) else ["step"]
    for field in number_fields:
        if field in changes:
            value = _finite(changes[field])
            if value is None or (field in ("step", "t_step") and value <= 0):
                continue
            if curve.get(field) != value:
                curve[field] = value
                changed = True

    close_mode = changes.get("close_mode")
    if curve_engine.is_parametric(curve) and close_mode in curve_engine.CLOSE_MODES:
        if curve.get("close_mode") != close_mode:
            curve["close_mode"] = close_mode
            changed = True

    variables = dict(curve.get("variables", {}))
    ranges = {k: list(v) for k, v in curve.get("variable_ranges", {}).items()}

    added = changes.get("add_variable")
    if isinstance(added, dict):
        name = added.get("name")
        error = check_variable_name(name, curve, params)
        if error is None:
            value = _finite(added.get("value"))
            variables[name] = 1.0 if value is None else value

    removed = changes.get("remove_variable")
    if isinstance(removed, str) and removed in variables:
        del variables[removed]
        ranges.pop(removed, None)

    new_values = changes.get("variables")
    if isinstance(new_values, dict):
        for name, raw in new_values.items():
            value = _finite(raw)
            if name in variables and value is not None:
                variables[name] = value
                # Typing a value outside the slider range widens the range instead of clamping it.
                if name in ranges:
                    ranges[name] = [min(ranges[name][0], value), max(ranges[name][1], value)]

    new_ranges = changes.get("variable_ranges")
    if isinstance(new_ranges, dict):
        for name, pair in new_ranges.items():
            if name not in variables or not isinstance(pair, (list, tuple)) or len(pair) != 2:
                continue
            low, high = _finite(pair[0]), _finite(pair[1])
            if low is None or high is None or low >= high:
                error = "Slider minimum must be smaller than maximum."
                continue
            ranges[name] = [low, high]

    if variables != curve.get("variables", {}):
        curve["variables"] = variables
        curve["variables_text"] = variables_text(variables)
        changed = True
    ranges = {k: v for k, v in ranges.items() if k in variables}
    if ranges != curve.get("variable_ranges", {}):
        curve["variable_ranges"] = ranges
        changed = True
    return changed, error


def handle_request(action, data, curves, params, new_curve):
    """Answer one request from the palette.

    new_curve(kind) returns a new default curve of that type.
    Returns (reply, saved): reply is JSON-serializable; saved is True when the library
    changed in a way that should be written to disk. Preview edits (slider drags,
    typing) change the curve in memory only until they are committed.
    """
    data = data if isinstance(data, dict) else {}
    view = data.get("view")
    hidden = data.get("hidden") or ()
    saved = False
    select = None
    message = None

    def valid_index(value):
        return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < len(curves)

    if action == "graphEdit":
        index = data.get("index")
        changes = data.get("changes")
        if not valid_index(index) or not isinstance(changes, dict):
            return {"error": "The function to edit was not found. Click Reload."}, False
        changed, message = apply_edit(curves[index], changes, params)
        saved = bool(data.get("commit")) or (changed and any(
            key in changes for key in ("type", "add_variable", "remove_variable", "variable_ranges", "close_mode")))
    elif action == "graphAdd":
        preset = data.get("preset")
        if isinstance(preset, int) and 0 <= preset < len(curve_library.PRESETS):
            curve = curve_library.curve_from_preset(curve_library.PRESETS[preset])
        else:
            kind = data.get("kind") if data.get("kind") in curve_engine.CURVE_TYPES else "implicit"
            curve = new_curve(kind)
        curve["name"] = curve_library.unique_name(curve["name"], [c.get("name") for c in curves])
        curves.append(curve)
        select = len(curves) - 1
        saved = True
    elif action == "graphDelete":
        index = data.get("index")
        if not valid_index(index):
            return {"error": "The function to delete was not found. Click Reload."}, False
        del curves[index]
        if not curves:
            curves.append(new_curve("implicit"))
        select = min(index, len(curves) - 1)
        saved = True
    elif action != "graphData":
        return {"error": f"Unknown request '{action}'."}, False

    reply = graph_payload(curves, params, view, hidden)
    if select is not None:
        reply["select"] = select
    if message:
        reply["message"] = message
    return reply, saved

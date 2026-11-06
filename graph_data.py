"""Data for the graph window: samples curves for the visible area and applies edits.

No Fusion dependency, so it can be unit-tested outside Fusion. The palette (graph.js)
sends a view rectangle and receives curve pieces in plain graph coordinates.
"""

import math

try:
    from . import curve_engine
except ImportError:
    import curve_engine


# Samples across the visible width (y = f(x)) or along the whole t range (parametric).
SAMPLES_PER_VIEW = 800
SAMPLES_PER_PARAMETRIC = 1500
GRAPH_LIMITS = {"time_budget_seconds": 0.5, "max_points_per_curve": 5000}

EDITABLE_NUMBER_FIELDS = ("t_start", "t_end")


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
    }


def variables_text(variables):
    return ",".join(f"{name}={value:g}" for name, value in variables.items())


def apply_edit(curve, changes):
    """Apply an edit from the palette in place. Returns True when anything changed.

    Only known fields are accepted; numbers must be finite. Variables can only be
    changed, not added, so the Library tab stays the place to define them.
    """
    changed = False
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

    if curve_engine.is_parametric(curve):
        for field in EDITABLE_NUMBER_FIELDS:
            if field in changes:
                value = _finite(changes[field])
                if value is not None and curve.get(field) != value:
                    curve[field] = value
                    changed = True

    new_variables = changes.get("variables")
    if isinstance(new_variables, dict):
        variables = dict(curve.get("variables", {}))
        for name, raw in new_variables.items():
            value = _finite(raw)
            if name in variables and value is not None and variables[name] != value:
                variables[name] = value
                changed = True
        if variables != curve.get("variables", {}):
            curve["variables"] = variables
            curve["variables_text"] = variables_text(variables)
    return changed


def handle_request(action, data, curves, params, new_curve):
    """Answer one request from the palette.

    Returns (reply, saved): reply is JSON-serializable; saved is True when the library
    changed in a way that should be written to disk (commits and new functions).
    Preview edits (slider drags) change the curve in memory only.
    """
    data = data if isinstance(data, dict) else {}
    view = data.get("view")
    hidden = data.get("hidden") or ()
    saved = False
    select = None

    if action == "graphEdit":
        index = data.get("index")
        changes = data.get("changes")
        if not isinstance(index, int) or not 0 <= index < len(curves) or not isinstance(changes, dict):
            return {"error": "The function to edit was not found. Click Reload."}, False
        apply_edit(curves[index], changes)
        saved = bool(data.get("commit"))
    elif action == "graphAdd":
        curves.append(new_curve())
        select = len(curves) - 1
        saved = True
    elif action != "graphData":
        return {"error": f"Unknown request '{action}'."}, False

    reply = graph_payload(curves, params, view, hidden)
    if select is not None:
        reply["select"] = select
    return reply, saved

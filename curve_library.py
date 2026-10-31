"""Saving, loading, and preset gallery for the Math Curve function library.

No Fusion dependency, so it can be unit-tested outside Fusion.
"""

import json
import math
import os
import sys
from datetime import datetime

try:
    from .curve_engine import CLOSE_LINE, CLOSE_MODES, CLOSE_OPEN, CLOSE_SMOOTH, CURVE_TYPES
except ImportError:
    from curve_engine import CLOSE_LINE, CLOSE_MODES, CLOSE_OPEN, CLOSE_SMOOTH, CURVE_TYPES

LIBRARY_FORMAT = "math-curve-library"
LIBRARY_VERSION = 1
LIBRARY_FILENAME = "function_library.json"
APP_FOLDER_NAME = "MathCurve2"


def default_storage_dir():
    """Per-user folder that survives add-in updates and reinstalls."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_FOLDER_NAME)


def default_library_path():
    return os.path.join(default_storage_dir(), LIBRARY_FILENAME)


def _number(value, default):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(value) or math.isinf(value):
        return default
    return value


def normalize_curve(data):
    """Return a clean curve dict, or None when data is not a usable curve."""
    if not isinstance(data, dict):
        return None
    kind = data.get("type", "implicit")
    if kind not in CURVE_TYPES:
        return None

    variables = {}
    raw_variables = data.get("variables", {})
    if isinstance(raw_variables, dict):
        for name, value in raw_variables.items():
            number = _number(value, None)
            if isinstance(name, str) and number is not None:
                variables[name] = number

    curve = {
        "name": str(data.get("name") or "Curve").strip() or "Curve",
        "type": kind,
        "variables_text": str(data.get("variables_text") or ""),
        "variables": variables,
        "enabled": False,
        "invert_origin": bool(data.get("invert_origin", False)),
        "invert_x": bool(data.get("invert_x", False)),
        "invert_y": bool(data.get("invert_y", False)),
    }
    if not curve["variables_text"] and variables:
        curve["variables_text"] = ",".join(f"{k}={v:g}" for k, v in variables.items())

    if kind == "implicit":
        curve["expr"] = str(data.get("expr") or "sin(x)")
        curve["step"] = _number(data.get("step"), 0.2)
    else:
        curve["x_expr"] = str(data.get("x_expr") or "cos(t)")
        curve["y_expr"] = str(data.get("y_expr") or "sin(t)")
        if kind == "parametric3d":
            curve["z_expr"] = str(data.get("z_expr") or "0")
        curve["t_start"] = _number(data.get("t_start"), 0.0)
        curve["t_end"] = _number(data.get("t_end"), 2 * math.pi)
        curve["t_step"] = _number(data.get("t_step"), 0.1)
        close_mode = data.get("close_mode", CLOSE_OPEN)
        curve["close_mode"] = close_mode if close_mode in CLOSE_MODES else CLOSE_OPEN
    return curve


def unique_name(name, existing_names):
    existing = set(existing_names)
    if name not in existing:
        return name
    index = 2
    while f"{name} ({index})" in existing:
        index += 1
    return f"{name} ({index})"


def serialize_library(curves):
    stored = []
    for curve in curves:
        clean = normalize_curve(curve)
        if clean:
            clean.pop("enabled", None)
            stored.append(clean)
    return {
        "format": LIBRARY_FORMAT,
        "version": LIBRARY_VERSION,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "curves": stored,
    }


def parse_library(payload):
    """Return (curves, skipped_count). Raises ValueError for files that are not a library."""
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("curves"), list):
        items = payload["curves"]
    else:
        raise ValueError("This file is not a Math Curve function library.")

    curves = []
    skipped = 0
    for item in items:
        curve = normalize_curve(item)
        if curve is None:
            skipped += 1
            continue
        curve["name"] = unique_name(curve["name"], [c["name"] for c in curves])
        curves.append(curve)
    return curves, skipped


def save_library(path, curves):
    """Write the library atomically so a crash never leaves a half-written file."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(serialize_library(curves), handle, indent=2, ensure_ascii=False)
    os.replace(temp_path, path)


def load_library(path):
    """Return (curves, message). Missing file -> ([], None). A broken file is kept as .broken."""
    if not os.path.isfile(path):
        return [], None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            curves, skipped = parse_library(json.load(handle))
    except (OSError, ValueError) as ex:
        broken_path = path + ".broken"
        try:
            os.replace(path, broken_path)
        except OSError:
            broken_path = path
        return [], f"The saved function library could not be read and was kept as {broken_path} ({ex})."
    message = f"{skipped} unreadable function(s) in the saved library were skipped." if skipped else None
    return curves, message


def merge_curves(existing, incoming):
    """Append incoming curves, renaming duplicates. Returns the number added."""
    names = [curve["name"] for curve in existing]
    for curve in incoming:
        curve = dict(curve)
        curve["name"] = unique_name(curve["name"], names)
        names.append(curve["name"])
        existing.append(curve)
    return len(incoming)


def _implicit(category, name, expr, variables, step=0.1):
    return {"category": category, "name": name, "type": "implicit", "expr": expr,
            "variables": variables, "step": step}


def _param(category, name, x_expr, y_expr, variables, t_end, t_step=0.05, close_mode=CLOSE_OPEN,
           t_start=0.0):
    return {"category": category, "name": name, "type": "parametric", "x_expr": x_expr,
            "y_expr": y_expr, "variables": variables, "t_start": t_start, "t_end": t_end,
            "t_step": t_step, "close_mode": close_mode}


def _param3d(category, name, x_expr, y_expr, z_expr, variables, t_end, t_step=0.05,
             close_mode=CLOSE_OPEN):
    data = _param(category, name, x_expr, y_expr, variables, t_end, t_step, close_mode)
    data["type"] = "parametric3d"
    data["z_expr"] = z_expr
    return data


TWO_PI = 2 * math.pi

PRESETS = [
    _implicit("Waves", "Sine Wave", "A*sin(2*pi*x/L)", {"A": 1, "L": 10}),
    _implicit("Waves", "Damped Wave", "A*exp(-k*x)*sin(2*pi*x/L)", {"A": 2, "k": 0.2, "L": 3}),
    _implicit("Waves", "Triangle Wave", "2*A/pi*asin(sin(2*pi*x/L))", {"A": 1, "L": 4}),
    _implicit("Basic", "Parabola", "a*x**2", {"a": 0.1}),
    _implicit("Basic", "Catenary", "a*cosh((x-c)/a)-a", {"a": 3, "c": 5}),
    _implicit("Basic", "Bell Curve", "A*exp(-((x-m)**2)/(2*s**2))", {"A": 3, "m": 5, "s": 1.5}),
    _implicit("Basic", "Smooth Step", "H/(1+exp(-k*(x-c)))", {"H": 2, "k": 2, "c": 5}),
    _param("Shapes", "Circle", "r*cos(t)", "r*sin(t)", {"r": 3}, TWO_PI, close_mode=CLOSE_SMOOTH),
    _param("Shapes", "Ellipse", "a*cos(t)", "b*sin(t)", {"a": 4, "b": 2}, TWO_PI,
           close_mode=CLOSE_SMOOTH),
    _param("Shapes", "Rose Curve", "r*cos(k*t)*cos(t)", "r*cos(k*t)*sin(t)", {"r": 3, "k": 4},
           TWO_PI, t_step=0.02, close_mode=CLOSE_SMOOTH),
    _param("Shapes", "Heart", "s*16*sin(t)**3",
           "s*(13*cos(t)-5*cos(2*t)-2*cos(3*t)-cos(4*t))", {"s": 0.2}, TWO_PI,
           close_mode=CLOSE_SMOOTH),
    _param("Shapes", "Astroid", "a*cos(t)**3", "a*sin(t)**3", {"a": 3}, TWO_PI, t_step=0.02,
           close_mode=CLOSE_SMOOTH),
    _param("Shapes", "Lissajous", "A*sin(a*t+d)", "B*sin(b*t)", {"A": 3, "B": 3, "a": 3, "b": 2,
           "d": 1.5708}, TWO_PI, t_step=0.02, close_mode=CLOSE_SMOOTH),
    _param("Mechanical", "Involute (Gear)", "r*(cos(t)+t*sin(t))", "r*(sin(t)-t*cos(t))",
           {"r": 2}, 1.2, t_step=0.02),
    _param("Mechanical", "Cycloid", "r*(t-sin(t))", "r*(1-cos(t))", {"r": 1}, 2 * TWO_PI),
    _param("Mechanical", "Hypotrochoid", "(R-r)*cos(t)+d*cos((R-r)/r*t)",
           "(R-r)*sin(t)-d*sin((R-r)/r*t)", {"R": 5, "r": 3, "d": 5}, 3 * TWO_PI, t_step=0.02,
           close_mode=CLOSE_SMOOTH),
    _param("Spirals", "Archimedean Spiral", "a*t*cos(t)", "a*t*sin(t)", {"a": 0.3}, 3 * TWO_PI),
    _param("Spirals", "Logarithmic Spiral", "a*exp(b*t)*cos(t)", "a*exp(b*t)*sin(t)",
           {"a": 0.5, "b": 0.15}, 3 * TWO_PI),
    _param3d("3D (beta)", "Helix", "r*cos(t)", "r*sin(t)", "p*t/(2*pi)", {"r": 2, "p": 1},
             4 * TWO_PI),
    _param3d("3D (beta)", "Conical Spiral", "a*t*cos(t)", "a*t*sin(t)", "c*t",
             {"a": 0.2, "c": 0.3}, 4 * TWO_PI),
    _param3d("3D (beta)", "Torus Knot", "(R+r*cos(q*t))*cos(p*t)", "(R+r*cos(q*t))*sin(p*t)",
             "r*sin(q*t)", {"R": 3, "r": 1, "p": 2, "q": 3}, TWO_PI, t_step=0.01,
             close_mode=CLOSE_SMOOTH),
]

CLOSE_MODE_LABELS = [
    (CLOSE_OPEN, "Open (do not connect)"),
    (CLOSE_SMOOTH, "Close smoothly"),
    (CLOSE_LINE, "Close with a straight line"),
]


def preset_label(preset):
    return f"{preset['category']}: {preset['name']}"


def curve_from_preset(preset):
    data = {k: v for k, v in preset.items() if k != "category"}
    return normalize_curve(data)

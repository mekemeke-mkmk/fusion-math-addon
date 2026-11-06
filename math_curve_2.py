import adsk.core
import adsk.fusion
import traceback
import math
import json
import os

from .license_manager import check_license, developer_diagnostics, developer_mode_enabled
from . import curve_engine
from . import curve_library
from . import graph_window
from . import model_preview

handlers = []
curves = []

MAIN_CMD_ID = "MathCurveSketch"
RELOAD_CMD_ID = "MathCurveSketchReload"
CREATE_CMD_ID = "MathCurveCreateCurves"
# Commands from earlier versions, removed when the add-in starts.
OLD_CMD_IDS = ("MathCurveGraph", "MathCurvePlaceFromGraph")
PANEL_ID = "SketchCreatePanel"
ICON_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "commands",
    "commandDialog",
    "resources",
    ""
)
RELOAD_ICON_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "commands",
    "reloadCommand",
    "resources",
    ""
)

# Centimeters (Fusion's internal length unit) per function unit.
UNIT_SCALES = {
    "mm": 0.1,
    "cm": 1.0,
    "m": 100.0,
    "in": 2.54,
    "ft": 30.48,
}

# Same order as COLORS in resources/graph/graph.js, so the viewport preview matches the graph.
CURVE_COLORS = ["#2f6fdf", "#e8590c", "#2b8a3e", "#ae3ec9", "#0c8599", "#c92a2a", "#8d5524", "#5c940d"]

POINT_TOLERANCE_CM = 1.0e-6

commandState = {
    "start": None,
    "end": None,
    "hover": None,
    "baselineToken": None,
    "baselineLine": None,  # Selected SketchLine; avoids a token lookup on every refresh
    "hasFinalEnd": False,
    "previewDirty": True,
    "rangeStart": 0.0,
    "rangeEnd": 10.0,
    "invertOrigin": False,
    "invertX": False,
    "invertY": False,
    "setupVarOverrides": {},
    "unit": None,  # None until the window sends one; then the document unit is the default
    "outputMode": "light",
    "previewEnabled": True,
    "ackSignature": None,  # Warnings the user accepted with "Draw anyway"
    "analysisCache": None,
    "paramsCache": None,  # (unit, params): reading Fusion parameters is slow, so read once per change
    "notice": None,  # Library load/save problems shown in the Status box
    "placementMode": None,  # None, "line" or "origin"
    "placementSketch": None,
    "flash": None  # One-time message for the window, e.g. after Create Curves
}


def default_curve():
    return {
        "name": f"Curve {len(curves) + 1}",
        "type": "implicit",  # Type: implicit (y=f(x)) or parametric (x(t), y(t))
        "expr": "sin(x)",
        "variables_text": "",
        "variables": {},
        "step": 0.2,
        "enabled": False,
        "invert_origin": False,
        "invert_x": False,
        "invert_y": False
    }


def default_parametric_curve():
    return {
        "name": f"Parametric Curve {len(curves) + 1}",
        "type": "parametric",
        "x_expr": "cos(t)",
        "y_expr": "sin(t)",
        "variables_text": "",
        "variables": {},
        "t_step": 0.1,
        "t_start": 0.0,
        "t_end": math.pi * 2,
        "close_mode": curve_engine.CLOSE_OPEN,
        "enabled": False,
        "invert_origin": False,
        "invert_x": False,
        "invert_y": False
    }


def default_parametric3d_curve():
    curve = default_parametric_curve()
    curve.update({
        "name": f"3D Curve {len(curves) + 1}",
        "type": "parametric3d",
        "z_expr": "t/(2*pi)",
        "t_end": math.pi * 4
    })
    return curve


def new_curve_of_type(kind):
    if kind == "parametric3d":
        return default_parametric3d_curve()
    if kind == "parametric":
        return default_parametric_curve()
    return default_curve()


def reset_point_state():
    commandState["start"] = None
    commandState["end"] = None
    commandState["hover"] = None
    commandState["baselineToken"] = None
    commandState["baselineLine"] = None
    commandState["hasFinalEnd"] = False
    commandState["previewDirty"] = True
    commandState["rangeStart"] = 0.0
    commandState["rangeEnd"] = 10.0
    commandState["invertOrigin"] = False
    commandState["invertX"] = False
    commandState["invertY"] = False


def get_active_sketch():
    app = adsk.core.Application.get()
    sketch = app.activeEditObject
    if sketch and sketch.objectType == adsk.fusion.Sketch.classType():
        return adsk.fusion.Sketch.cast(sketch)
    return None


def get_active_design():
    app = adsk.core.Application.get()
    return adsk.fusion.Design.cast(app.activeProduct)


def unit_scale():
    return UNIT_SCALES.get(commandState.get("unit"), 1.0)


def document_length_unit(design):
    try:
        unit = design.unitsManager.defaultLengthUnits
    except:
        return "cm"
    return unit if unit in UNIT_SCALES else "cm"


def get_user_params(design):
    """User parameters for expressions. Length parameters are converted to the selected unit."""
    params = {}
    if not design:
        return params

    cached = commandState.get("paramsCache")
    if cached and cached[0] == commandState.get("unit"):
        return dict(cached[1])

    units_manager = design.unitsManager
    scale = unit_scale()
    for p in design.userParameters:
        value = p.value
        try:
            if p.unit and units_manager.isValidExpression(f"1 {p.unit}", "cm"):
                value = value / scale
        except:
            pass
        params[p.name] = value
    commandState["paramsCache"] = (commandState.get("unit"), dict(params))
    return params


def current_end_point():
    if commandState["hasFinalEnd"] and commandState["end"]:
        return commandState["end"]
    return commandState["hover"]


def range_is_final():
    return commandState["start"] is not None and commandState["end"] is not None and commandState["hasFinalEnd"]


def get_baseline_from_token():
    """トークンからベースラインを取得。詳細なエラー情報を記録"""
    line = commandState.get("baselineLine")
    try:
        if line and line.isValid:
            return line
    except:
        pass
    token = commandState["baselineToken"]
    design = get_active_design()
    if not token or not design:
        return None

    try:
        entities = design.findEntityByToken(token)
    except Exception as e:
        # エラーの種類を区別可能に（デバッグ用）
        # ui.messageBox(f"Token lookup failed: {str(e)}")
        return None

    if not entities or len(entities) < 1:
        return None

    try:
        entity = entities[0]
        if entity and entity.objectType == adsk.fusion.SketchLine.classType():
            return adsk.fusion.SketchLine.cast(entity)
    except:
        pass

    return None


def update_state_from_baseline(line):
    if not line or not line.isValid:
        reset_point_state()
        return False

    start_geo = line.startSketchPoint.geometry
    end_geo = line.endSketchPoint.geometry
    old_start = commandState["start"]
    old_end = commandState["end"]
    unchanged = (
        commandState["hasFinalEnd"] and old_start and old_end
        and (old_start.x, old_start.y, old_end.x, old_end.y) == (start_geo.x, start_geo.y, end_geo.x, end_geo.y)
    )
    commandState["baselineLine"] = line
    if unchanged:
        return True
    commandState["start"] = adsk.core.Point3D.create(start_geo.x, start_geo.y, 0)
    commandState["end"] = adsk.core.Point3D.create(end_geo.x, end_geo.y, 0)
    commandState["hover"] = commandState["end"]
    try:
        commandState["baselineToken"] = line.entityToken
    except:
        commandState["baselineToken"] = None
    commandState["hasFinalEnd"] = True
    commandState["previewDirty"] = True
    return True


def build_frame():
    start = commandState["start"]
    end = current_end_point()
    if not start or not end:
        return None

    # 反対側原点オプション
    if commandState["invertOrigin"]:
        start, end = end, start

    dx = end.x - start.x
    dy = end.y - start.y
    length = math.hypot(dx, dy)
    if length <= 1.0e-6:
        return None

    ux = dx / length
    uy = dy / length
    px = -uy
    py = ux

    # x軸反転
    if commandState["invertX"]:
        ux = -ux
        uy = -uy

    # y軸反転
    if commandState["invertY"]:
        px = -px
        py = -py

    return {
        "start": start,
        "end": end,
        "guideLength": length,
        "angle": math.atan2(dy, dx),
        "u": (ux, uy),
        "p": (px, py)
    }


def analyze_curves(design):
    """Sample every enabled curve in function units. Cached until an input changes."""
    params = get_user_params(design)
    x_range = (commandState["rangeStart"], commandState["rangeEnd"])
    enabled = [(index, curve) for index, curve in enumerate(curves) if curve.get("enabled", False)]
    overrides = commandState.get("setupVarOverrides", {})
    cache_key = repr((enabled, x_range, sorted(params.items()), sorted(overrides.items()), unit_scale()))
    cached = commandState.get("analysisCache")
    if cached and cached[0] == cache_key:
        return cached[1]

    results = []
    max_abs = curve_engine.LIMITS["max_abs_value_cm"] / unit_scale()
    for index, curve in enabled:
        curve_for_run = dict(curve)
        variables = dict(curve.get("variables", {}))
        for var_name in variables:
            override_key = f"{curve.get('name', '')}::{var_name}"
            if override_key in overrides:
                variables[var_name] = overrides[override_key]
        curve_for_run["variables"] = variables
        result = curve_engine.sample_curve(curve_for_run, params, x_range, max_abs_value=max_abs)
        result.library_index = index
        results.append(result)

    total_points = sum(result.point_count for result in results if not result.errors)
    report = {"results": results, "global_warnings": []}
    if total_points > curve_engine.LIMITS["warn_points_total"]:
        report["global_warnings"].append(
            f"{total_points} points in total. Drawing may make Fusion slow; consider a larger Step."
        )
    commandState["analysisCache"] = (cache_key, report)
    return report


def warning_signature(report):
    items = list(report["global_warnings"])
    for result in report["results"]:
        if not result.errors:
            items.extend(f"{result.name}: {warning}" for warning in result.warnings)
    return tuple(items)


def warnings_acknowledged(report):
    signature = warning_signature(report)
    return not signature or commandState.get("ackSignature") == signature


def curves_to_draw(report):
    """Results that may be drawn now: no errors, and warnings only when accepted."""
    if not warnings_acknowledged(report):
        return [r for r in report["results"] if r.drawable and not r.warnings]
    return [r for r in report["results"] if r.drawable]


def report_blocks_creation(report):
    if not report["results"]:
        return True
    if any(result.errors for result in report["results"]):
        return True
    return not warnings_acknowledged(report)


def format_report(report):
    lines = []
    if developer_mode_enabled():
        lines.append("[DEV] Developer mode: the Marketplace license check is skipped on this PC.")
    notice = commandState.get("notice")
    if notice:
        lines.append(f"[NOTE] {notice}")
    if not report["results"]:
        lines.append("Select at least one function with Draw.")
    for result in report["results"]:
        if result.errors:
            lines.append(f"[ERROR] {result.name}: " + " ".join(result.errors))
        elif result.warnings:
            lines.append(f"[WARNING] {result.name}: " + " ".join(result.warnings))
        else:
            lines.append(f"[OK] {result.name}: {result.point_count} points")
    for warning in report["global_warnings"]:
        lines.append(f"[WARNING] {warning}")

    if any(result.errors for result in report["results"]):
        lines.append("Fix the errors above (select the function to see why) before creating curves.")
    elif not warnings_acknowledged(report):
        lines.append("Stopped: review the warnings, then check 'Draw anyway' to continue.")
    return "\n".join(lines)


def to_sketch_points(result, frame, piece):
    """Convert one piece (function units) to sketch points along the baseline frame."""
    start = frame["start"]
    ux, uy = frame["u"]
    px, py = frame["p"]
    if result.invert_origin:
        start = frame["end"]
        ux = -ux
        uy = -uy
    if result.invert_x:
        ux = -ux
        uy = -uy
    if result.invert_y:
        px = -px
        py = -py

    scale = unit_scale()
    points = []
    for a, b, c in piece:
        points.append((
            start.x + (ux * a + px * b) * scale,
            start.y + (uy * a + py * b) * scale,
            c * scale
        ))
    return curve_engine.remove_duplicate_points(points, POINT_TOLERANCE_CM)


def collect_curve_samples(design, frame):
    """Return [(result, [[(x, y, z), ...], ...])] in sketch coordinates for drawable curves."""
    report = analyze_curves(design)
    return [
        (result, [to_sketch_points(result, frame, piece) for piece in result.pieces])
        for result in curves_to_draw(report)
    ]


def make_point_collection(points):
    collection = adsk.core.ObjectCollection.create()
    for x, y, z in points:
        collection.add(adsk.core.Point3D.create(x, y, z))
    return collection


def add_curve_geometry(sketch, result, pieces, created):
    """Add splines for one curve. Closes the curve if requested. Appends new entities to created."""
    splines = sketch.sketchCurves.sketchFittedSplines
    close_mode = result.close_mode if len(pieces) == 1 else curve_engine.CLOSE_OPEN
    light = commandState.get("outputMode") == "light"
    for points in pieces:
        if len(points) < 2:
            continue
        if light:
            spline = add_light_spline(sketch, points, close_mode == curve_engine.CLOSE_SMOOTH)
            created.append(spline)
            if close_mode == curve_engine.CLOSE_LINE:
                created.append(sketch.sketchCurves.sketchLines.addByTwoPoints(spline.endSketchPoint, spline.startSketchPoint))
            continue
        if close_mode != curve_engine.CLOSE_OPEN and curve_engine.endpoints_coincide(points, POINT_TOLERANCE_CM * 10):
            points = points[:-1]

        if close_mode == curve_engine.CLOSE_SMOOTH and len(points) >= 3:
            spline = splines.add(make_point_collection(points))
            created.append(spline)
            try:
                spline.isClosed = True
            except:
                # Fallback: end at the start point (corner instead of a smooth join).
                spline.deleteMe()
                created.pop()
                spline = splines.add(make_point_collection(points + [points[0]]))
                created.append(spline)
            continue

        spline = splines.add(make_point_collection(points))
        created.append(spline)
        if close_mode == curve_engine.CLOSE_LINE and len(points) >= 2:
            closing = sketch.sketchCurves.sketchLines.addByTwoPoints(spline.endSketchPoint, spline.startSketchPoint)
            created.append(closing)


def thin_points(points, max_count):
    """Keep evenly spaced points (always the first and last) so preview splines stay light."""
    if len(points) <= max_count:
        return points
    step = (len(points) - 1) / (max_count - 1)
    return [points[round(i * step)] for i in range(max_count)]


def add_light_spline(sketch, points, closed=False):
    """One fixed spline through the points, without fit points.

    A fitted spline adds a sketch point per sample, and Fusion re-solves all of them on every
    later preview, so the command gets slower each time curves are created. This stays light.
    """
    controls, degree, knots = curve_engine.interpolating_nurbs(points, closed)
    nurbs = adsk.core.NurbsCurve3D.createNonRational(
        [adsk.core.Point3D.create(x, y, z) for x, y, z in controls], degree, knots, False
    )
    return sketch.sketchCurves.sketchFixedSplines.addByNurbsCurve(nurbs)


def create_final_curves(sketch, design):
    frame = build_frame()
    if not frame:
        return False

    samples = collect_curve_samples(design, frame)
    if not samples:
        return False

    if commandState.get("placementMode") == "origin":
        # With a selected line the line itself is the reference; at the origin, leave an x axis.
        axis_line = sketch.sketchCurves.sketchLines.addByTwoPoints(frame["start"], frame["end"])
        axis_line.isConstruction = True

    failed = []
    try:
        sketch.isComputeDeferred = True
    except:
        pass
    try:
        for result, pieces in samples:
            try:
                add_curve_geometry(sketch, result, pieces, [])
            except Exception as ex:
                failed.append(f"{result.name}: {ex}")
    finally:
        try:
            sketch.isComputeDeferred = False
        except:
            pass

    if failed:
        app = adsk.core.Application.get()
        app.userInterface.messageBox(
            "Some curves could not be created in Fusion:\n" + "\n".join(failed),
            "Math Curve"
        )
    return True


def persist_library(notify_graph=True):
    """Save the library after every change so it survives a Fusion restart."""
    try:
        curve_library.save_library(curve_library.default_library_path(), curves)
        if (commandState.get("notice") or "").startswith("Could not save"):
            commandState["notice"] = None
    except Exception as ex:
        commandState["notice"] = f"Could not save the function library: {ex}"
    if notify_graph:
        graph_window.notify_library_changed()


def new_library_curve(kind="implicit"):
    curve = new_curve_of_type(kind)
    curve["name"] = curve_library.unique_name(curve["name"], [c["name"] for c in curves])
    return curve


def set_origin_placement():
    """Use the sketch origin and the sketch X axis instead of a selected line."""
    length = max(abs(commandState["rangeEnd"] - commandState["rangeStart"]) * unit_scale(), 1.0)
    commandState["start"] = adsk.core.Point3D.create(0, 0, 0)
    commandState["end"] = adsk.core.Point3D.create(length, 0, 0)
    commandState["hover"] = commandState["end"]
    commandState["baselineToken"] = None
    commandState["baselineLine"] = None
    commandState["hasFinalEnd"] = True
    commandState["previewDirty"] = True


def load_saved_library():
    loaded, message = curve_library.load_library(curve_library.default_library_path())
    curves[:] = loaded or [default_curve()]
    commandState["notice"] = message


def library_file_dialog(save):
    ui = adsk.core.Application.get().userInterface
    dialog = ui.createFileDialog()
    dialog.filter = "Math Curve Library (*.json)"
    dialog.title = "Export Function Library" if save else "Import Function Library"
    if save:
        dialog.initialFilename = "math_curve_library.json"
        result = dialog.showSave()
    else:
        dialog.isMultiSelectEnabled = False
        result = dialog.showOpen()
    if result != adsk.core.DialogResults.DialogOK:
        return None
    return dialog.filename


def export_library():
    path = library_file_dialog(save=True)
    if not path:
        return
    ui = adsk.core.Application.get().userInterface
    try:
        curve_library.save_library(path, curves)
        ui.messageBox(f"Exported {len(curves)} function(s) to:\n{path}", "Math Curve")
    except Exception as ex:
        ui.messageBox(f"Export failed: {ex}", "Math Curve")


def import_library():
    path = library_file_dialog(save=False)
    if not path:
        return
    ui = adsk.core.Application.get().userInterface
    try:
        with open(path, "r", encoding="utf-8") as handle:
            imported, skipped = curve_library.parse_library(json.load(handle))
    except Exception as ex:
        ui.messageBox(f"Import failed: {ex}", "Math Curve")
        return
    if not imported:
        ui.messageBox("The file contains no usable functions.", "Math Curve")
        return
    curve_library.merge_curves(curves, imported)
    persist_library()
    message = f"Imported {len(imported)} function(s)."
    if skipped:
        message += f" {skipped} unreadable function(s) were skipped."
    ui.messageBox(message, "Math Curve")


def delete_control_if_exists(panel, control_id):
    control = panel.controls.itemById(control_id)
    if control:
        control.deleteMe()


def delete_definition_if_exists(ui, command_id):
    cmd_def = ui.commandDefinitions.itemById(command_id)
    if cmd_def:
        cmd_def.deleteMe()


def get_reload_icon_folder():
    required_files = ("16x16.png", "32x32.png", "64x64.png")
    if os.path.isdir(RELOAD_ICON_FOLDER) and all(
        os.path.isfile(os.path.join(RELOAD_ICON_FOLDER, name)) for name in required_files
    ):
        return RELOAD_ICON_FOLDER
    return ICON_FOLDER


def create_or_replace_button(panel, cmd_def):
    delete_control_if_exists(panel, cmd_def.id)
    control = panel.controls.addCommand(cmd_def)
    control.isPromoted = True
    return control


def apply_window_settings(settings):
    """Settings sent with every request from the window: unit, x range, output, preview, Draw anyway."""
    if not isinstance(settings, dict):
        settings = {}
    unit = settings.get("unit")
    if unit not in UNIT_SCALES:
        unit = commandState.get("unit") or document_length_unit(get_active_design())
    if unit != commandState.get("unit"):
        commandState["unit"] = unit
        commandState["paramsCache"] = None
    try:
        x_start = float(settings.get("x_start"))
        x_end = float(settings.get("x_end"))
        if math.isfinite(x_start) and math.isfinite(x_end) and x_start != x_end:
            commandState["rangeStart"], commandState["rangeEnd"] = x_start, x_end
    except (TypeError, ValueError):
        pass
    commandState["outputMode"] = "editable" if settings.get("output") == "editable" else "light"
    commandState["previewEnabled"] = settings.get("preview", True) is not False
    if settings.get("ack") is True:
        if commandState.get("ackSignature") is None:
            commandState["ackSignature"] = warning_signature(analyze_curves(get_active_design()))
    else:
        commandState["ackSignature"] = None


def clear_window_placement():
    reset_point_state()
    commandState["placementMode"] = None
    commandState["placementSketch"] = None
    commandState["baselineLine"] = None
    model_preview.clear()


def refresh_placement():
    """Re-read the baseline (the line may have been edited). Returns the target sketch or None."""
    mode = commandState.get("placementMode")
    try:
        if mode == "line":
            line = get_baseline_from_token()
            if line and line.isValid:
                update_state_from_baseline(line)
                return line.parentSketch
            clear_window_placement()
            commandState["flash"] = "The selected line no longer exists. Select a line again."
        elif mode == "origin":
            sketch = commandState.get("placementSketch")
            if sketch and sketch.isValid:
                set_origin_placement()
                return sketch
            clear_window_placement()
    except:
        clear_window_placement()
    return None


def placement_text(sketch):
    mode = commandState.get("placementMode")
    if not sketch or not mode:
        return "Not set. Click Select line, or Sketch origin while editing a sketch."
    if mode == "origin":
        return f"Origin and X axis of {sketch.name}"
    frame = build_frame()
    if not frame:
        return f"Line in {sketch.name}"
    length = frame["guideLength"] / unit_scale()
    return f"Line in {sketch.name}: {length:.4g} {commandState['unit']}, {math.degrees(frame['angle']):.1f}°"


def update_model_preview(design, sketch):
    """Draw the checked curves on the baseline as viewport-only graphics."""
    frame = build_frame() if sketch else None
    if not commandState.get("previewEnabled", True) or not frame:
        model_preview.clear()
        return
    try:
        drawn = []
        for result, pieces in collect_curve_samples(design, frame):
            strips = [list(piece) for piece in pieces if len(piece) >= 2]
            if result.close_mode != curve_engine.CLOSE_OPEN and len(strips) == 1:
                strips[0].append(strips[0][0])
            color = CURVE_COLORS[getattr(result, "library_index", 0) % len(CURVE_COLORS)]
            drawn.append((color, strips))
        start = frame["start"]
        ux, uy = frame["u"]
        length = abs(commandState["rangeEnd"] - commandState["rangeStart"]) * unit_scale()
        guides = [
            [(start.x, start.y, 0.0), (frame["end"].x, frame["end"].y, 0.0)],
            [(start.x, start.y, 0.0), (start.x + ux * length, start.y + uy * length, 0.0)],
        ]
        model_preview.show(design, sketch, drawn, guides)
    except:
        model_preview.clear()


def window_state():
    """Placement, status, and whether Create Curves is possible: sent with every reply."""
    design = get_active_design()
    sketch = refresh_placement()
    report = analyze_curves(design)
    signature = warning_signature(report)
    can_create = bool(sketch) and range_is_final() and not report_blocks_creation(report)
    update_model_preview(design, sketch)
    flash = commandState.get("flash")
    commandState["flash"] = None
    return {
        "placement": placement_text(sketch),
        "has_placement": bool(sketch),
        "status": format_report(report).split("\n"),
        "has_warnings": bool(signature),
        "ack": bool(signature) and warnings_acknowledged(report),
        "can_create": can_create,
        "unit": commandState["unit"],
        "flash": flash,
    }


def select_baseline_line():
    ui = adsk.core.Application.get().userInterface
    try:
        selection = ui.selectEntity(
            "Select a sketch line. Its start point is the origin and its direction is +x.", "SketchLines"
        )
    except:
        selection = None
    if not selection:
        return {"info": "Line selection was cancelled."}
    line = adsk.fusion.SketchLine.cast(selection.entity)
    if not line:
        return {"error": "Select a sketch line."}
    reset_point_state()
    commandState["placementMode"] = "line"
    commandState["placementSketch"] = line.parentSketch
    update_state_from_baseline(line)
    return {}


def use_sketch_origin():
    sketch = get_active_sketch()
    if not sketch:
        return {"error": "Edit a sketch first (double-click it in the browser), then click Sketch origin."}
    reset_point_state()
    commandState["placementMode"] = "origin"
    commandState["placementSketch"] = sketch
    set_origin_placement()
    return {}


def handle_window_action(action, data):
    """Fusion-side actions of the window. Returns extra reply fields ({"error": ...} on failure)."""
    if action == "mcSelectLine":
        return select_baseline_line()
    if action == "mcUseOrigin":
        return use_sketch_origin()
    if action == "mcClearPlacement":
        clear_window_placement()
        return {}
    if action == "mcExport":
        export_library()
        return {}
    if action == "mcImport":
        import_library()
        return {}
    if action == "mcCreate":
        ui = adsk.core.Application.get().userInterface
        cmd_def = ui.commandDefinitions.itemById(CREATE_CMD_ID)
        if not cmd_def:
            return {"error": "Restart the add-in: the create command is missing."}
        cmd_def.execute()
        return {"info": "Creating curves..."}
    return {"error": f"Unknown action '{action}'."}


def create_curves_now():
    """Create the checked curves on the baseline. Runs inside a command so it is one undo step."""
    app = adsk.core.Application.get()
    ui = app.userInterface
    design = get_active_design()
    sketch = refresh_placement()
    if not sketch or not range_is_final():
        ui.messageBox("Select a baseline line or the sketch origin in the Math Curve window first.", "Math Curve")
        return

    license_status = check_license(app)
    if not license_status.allowed:
        message = license_status.message
        diagnostics = developer_diagnostics()
        if diagnostics:
            message += "\n\n" + diagnostics
        ui.messageBox(message, "Math Curve License")
        return

    report = analyze_curves(design)
    if report_blocks_creation(report):
        ui.messageBox(format_report(report), "Math Curve")
        return

    model_preview.clear()
    if create_final_curves(sketch, design):
        count = len(curves_to_draw(report))
        commandState["flash"] = f"Created {count} curve(s) in {sketch.name}. Select another line to place them again."
        clear_window_placement()
    else:
        ui.messageBox("No curve could be created. Check the functions, variables, and range.", "Math Curve")
    graph_window.notify_library_changed()


def configure_window():
    graph_window.configure(
        get_curves=lambda: curves,
        get_params=lambda: get_user_params(get_active_design()),
        new_curve=new_library_curve,
        on_saved=lambda: persist_library(notify_graph=False),
        apply_settings=apply_window_settings,
        window_state=window_state,
        on_action=handle_window_action,
        on_closed=clear_window_placement
    )


def remove_ui():
    app = adsk.core.Application.get()
    ui = app.userInterface
    panel = ui.allToolbarPanels.itemById(PANEL_ID)
    for command_id in (MAIN_CMD_ID, RELOAD_CMD_ID, CREATE_CMD_ID) + OLD_CMD_IDS:
        if panel:
            delete_control_if_exists(panel, command_id)
        delete_definition_if_exists(ui, command_id)


def add_command(ui, command_id, name, tooltip, icon_folder, on_execute):
    """Button definition whose command has no dialog: execute fires right away."""
    delete_definition_if_exists(ui, command_id)
    cmd_def = ui.commandDefinitions.addButtonDefinition(command_id, name, tooltip, icon_folder)
    on_created = InstantCommandCreatedHandler(on_execute)
    cmd_def.commandCreated.add(on_created)
    handlers.append(on_created)
    return cmd_def


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    try:
        if not curves:
            load_saved_library()
        remove_ui()
        configure_window()
        panel = ui.allToolbarPanels.itemById(PANEL_ID)

        main_def = add_command(
            ui, MAIN_CMD_ID, "Math Curve Sketch",
            "Open the Math Curve window: define functions, check them on a graph, and create them in the sketch.",
            ICON_FOLDER, graph_window.show
        )
        reload_def = add_command(
            ui, RELOAD_CMD_ID, "Reload Math Curve",
            "Recovery button for Math Curve. Reload the function library and reopen the window.",
            get_reload_icon_folder(), reload_window
        )
        # Started from the window's Create Curves button, so it has no toolbar button.
        add_command(ui, CREATE_CMD_ID, "Create Math Curves", "Create the checked functions in the sketch.",
                    ICON_FOLDER, create_curves_now)

        create_or_replace_button(panel, main_def)
        create_or_replace_button(panel, reload_def)
    except:
        ui.messageBox(traceback.format_exc())


def reload_window():
    load_saved_library()
    commandState["analysisCache"] = None
    commandState["paramsCache"] = None
    graph_window.stop()
    graph_window.show()


def stop(context):
    global handlers
    clear_window_placement()
    graph_window.stop()
    handlers = []
    remove_ui()


class InstantExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self, action):
        super().__init__()
        self.action = action

    def notify(self, args):
        try:
            self.action()
        except:
            adsk.core.Application.get().userInterface.messageBox(traceback.format_exc())


class InstantCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self, action):
        super().__init__()
        self.action = action

    def notify(self, args):
        try:
            args.command.isRepeatable = False
            on_execute = InstantExecuteHandler(self.action)
            args.command.execute.add(on_execute)
            handlers.append(on_execute)
        except:
            adsk.core.Application.get().userInterface.messageBox(traceback.format_exc())

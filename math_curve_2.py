import adsk.core
import adsk.fusion
import traceback
import math
import json
import os
import re
from datetime import datetime

from .license_manager import check_license
from . import curve_engine
from . import curve_library

handlers = []
curves = []
selectedIndex = 0

MAIN_CMD_ID = "MathCurveSketch"
RELOAD_CMD_ID = "MathCurveSketchReload"
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

previewCurves = []
previewGuides = []

SNAP_PIXEL_RADIUS = 14.0

# Centimeters (Fusion's internal length unit) per function unit.
UNIT_SCALES = {
    "mm": 0.1,
    "cm": 1.0,
    "m": 100.0,
    "in": 2.54,
    "ft": 30.48,
}
UNIT_ORDER = ("mm", "cm", "m", "in", "ft")

CURVE_TYPE_LABELS = [
    ("implicit", "y = f(x)"),
    ("parametric", "x(t), y(t)"),
    ("parametric3d", "x(t), y(t), z(t)  (beta)"),
]

POINT_TOLERANCE_CM = 1.0e-6

licenseState = {
    "checked": False,
    "allowed": False,
    "mode": "unknown",
    "message": ""
}

commandState = {
    "start": None,
    "end": None,
    "hover": None,
    "snapPoint": None,
    "baselineToken": None,
    "hasFinalEnd": False,
    "previewDirty": True,
    "rangeStart": 0.0,
    "rangeEnd": 10.0,
    "invertOrigin": False,
    "invertX": False,
    "invertY": False,
    "isParametricMode": False,  # True for any parametric type (2D or 3D)
    "curveType": "implicit",  # Type used by "Add Function"
    "setupVarOverrides": {},
    "unit": "cm",
    "ackSignature": None,  # Warnings the user accepted with "Draw anyway"
    "analysisCache": None,
    "notice": None  # Library load/save problems shown in the Status box
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
    commandState["snapPoint"] = None
    commandState["baselineToken"] = None
    commandState["hasFinalEnd"] = False
    commandState["previewDirty"] = True
    commandState["rangeStart"] = 0.0
    commandState["rangeEnd"] = 10.0
    commandState["invertOrigin"] = False
    commandState["invertX"] = False
    commandState["invertY"] = False


def reset_curve_selection():
    for curve in curves:
        curve["enabled"] = False


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
    return params


def parse_variables_text(text):
    variables = {}
    if not text:
        return variables
    parts = [p.strip() for p in text.split(",")]
    for part in parts:
        if not part or "=" not in part:
            continue
        name, raw_value = part.split("=", 1)
        name = name.strip()
        raw_value = raw_value.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            continue
        if name in curve_engine.RESERVED_NAMES:
            continue
        try:
            value = float(raw_value)
        except:
            continue
        variables[name] = value
    return variables


def is_parametric_mode_active():
    return bool(commandState.get("isParametricMode", False))


def get_command_input(inputs, input_id):
    try:
        return inputs.itemById(input_id)
    except:
        return None


def sync_parametric_inputs_enabled(inputs):
    enabled = is_parametric_mode_active()
    for input_id in ("xExpr", "yExpr", "tStart", "tEnd", "tStep", "closeMode"):
        target = get_command_input(inputs, input_id)
        if target:
            target.isEnabled = enabled

    z_input = get_command_input(inputs, "zExpr")
    if z_input:
        z_input.isEnabled = commandState.get("curveType") == "parametric3d"

    for input_id in ("expr", "step"):
        target = get_command_input(inputs, input_id)
        if target:
            target.isEnabled = not enabled


def format_point(point):
    if not point:
        return "Not set"
    return f"({point.x:.3f}, {point.y:.3f})"


def current_end_point():
    if commandState["hasFinalEnd"] and commandState["end"]:
        return commandState["end"]
    return commandState["hover"]


def range_is_defined():
    start = commandState["start"]
    end = current_end_point()
    if not start or not end:
        return False
    return math.hypot(end.x - start.x, end.y - start.y) > 1.0e-6


def range_is_final():
    return commandState["start"] is not None and commandState["end"] is not None and commandState["hasFinalEnd"]


def get_selected_baseline(inputs):
    selection_input = adsk.core.SelectionCommandInput.cast(inputs.itemById("baselineLine"))
    if not selection_input or selection_input.selectionCount < 1:
        return None

    selection = selection_input.selection(0)
    if not selection:
        return None

    entity = selection.entity
    if not entity or entity.objectType != adsk.fusion.SketchLine.classType():
        return None

    return adsk.fusion.SketchLine.cast(entity)


def get_baseline_from_token():
    """トークンからベースラインを取得。詳細なエラー情報を記録"""
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
    commandState["start"] = adsk.core.Point3D.create(start_geo.x, start_geo.y, 0)
    commandState["end"] = adsk.core.Point3D.create(end_geo.x, end_geo.y, 0)
    commandState["hover"] = commandState["end"]
    commandState["snapPoint"] = None
    try:
        commandState["baselineToken"] = line.entityToken
    except:
        commandState["baselineToken"] = None
    commandState["hasFinalEnd"] = True
    commandState["previewDirty"] = True
    return True


def clear_preview():
    for curve in previewCurves:
        if curve and curve.isValid:
            curve.deleteMe()
    previewCurves.clear()

    for guide in previewGuides:
        if guide and guide.isValid:
            guide.deleteMe()
    previewGuides.clear()


def render_preview():
    sketch = get_active_sketch()
    design = get_active_design()
    if not sketch:
        return False

    result = draw_preview(sketch, design)
    app = adsk.core.Application.get()
    if app.activeViewport:
        app.activeViewport.refresh()
    return result


def get_sketch_plane_point_model(sketch):
    return sketch.sketchToModelSpace(adsk.core.Point3D.create(0, 0, 0))


def view_to_sketch_point(viewport, viewport_position):
    sketch = get_active_sketch()
    if not sketch or not viewport or not viewport_position:
        return None

    plane_point = get_sketch_plane_point_model(sketch)
    x_axis = sketch.xDirection
    y_axis = sketch.yDirection
    normal = x_axis.crossProduct(y_axis)
    if not normal or normal.length <= 1.0e-9:
        return None
    normal.normalize()

    view_point = viewport.viewToModelSpace(viewport_position)
    camera = viewport.camera
    eye = camera.eye
    target = camera.target

    if hasattr(camera, "isPerspective") and not camera.isPerspective:
        ray_origin = view_point
        direction = eye.vectorTo(target)
    else:
        ray_origin = eye
        direction = eye.vectorTo(view_point)

    denom = normal.dotProduct(direction)

    if abs(denom) <= 1.0e-9:
        model_point = view_point
    else:
        offset = ray_origin.vectorTo(plane_point)
        t = normal.dotProduct(offset) / denom
        model_point = adsk.core.Point3D.create(
            ray_origin.x + direction.x * t,
            ray_origin.y + direction.y * t,
            ray_origin.z + direction.z * t
        )

    sketch_point = sketch.modelToSketchSpace(model_point)
    return adsk.core.Point3D.create(sketch_point.x, sketch_point.y, 0)


def snap_to_existing_point(sketch, viewport, viewport_position, fallback_point):
    """スナップ対象のポイントを探す。マウス移動時の毎回呼び出しのため最適化が重要"""
    if not sketch or not viewport or not viewport_position or not fallback_point:
        return fallback_point, None

    best_point = None
    best_distance = SNAP_PIXEL_RADIUS + 1.0  # 初期値を範囲外に設定

    candidates = [adsk.core.Point3D.create(0, 0, 0)]
    try:
        for sketch_point in sketch.sketchPoints:
            if sketch_point and sketch_point.isValid:
                geo = sketch_point.geometry
                candidates.append(adsk.core.Point3D.create(geo.x, geo.y, geo.z))
    except:
        pass  # スケッチポイントのアクセスに失敗

    for candidate in candidates:
        try:
            model_point = sketch.sketchToModelSpace(candidate)
            screen_point = viewport.modelToViewSpace(model_point)
            if not screen_point:
                continue

            dx = screen_point.x - viewport_position.x
            dy = screen_point.y - viewport_position.y
            distance = math.hypot(dx, dy)
            
            # 最短距離を記録（距離チェック時に内側に入ったら即座にループを抜ける）
            if distance < best_distance:
                best_distance = distance
                best_point = candidate
                if distance < 1.0:  # 十分に近ければ探索を早期終了
                    break
        except:
            continue  # 個別ポイントの変換失敗は無視

    if best_point and best_distance <= SNAP_PIXEL_RADIUS:
        snapped = adsk.core.Point3D.create(best_point.x, best_point.y, 0)
        return snapped, snapped

    return fallback_point, None


def resolve_input_point(viewport, viewport_position):
    sketch = get_active_sketch()
    raw_point = view_to_sketch_point(viewport, viewport_position)
    if not raw_point:
        return None

    snapped_point, snap_point = snap_to_existing_point(sketch, viewport, viewport_position, raw_point)
    commandState["snapPoint"] = snap_point
    return snapped_point


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


def set_end_from_polar(angle, length, final_value):
    start = commandState["start"]
    if not start:
        return

    end = adsk.core.Point3D.create(
        start.x + math.cos(angle) * length,
        start.y + math.sin(angle) * length,
        0
    )

    if final_value:
        commandState["end"] = end
        commandState["hasFinalEnd"] = True
    else:
        commandState["hover"] = end
        commandState["hasFinalEnd"] = False

    commandState["previewDirty"] = True


def analyze_curves(design):
    """Sample every enabled curve in function units. Cached until an input changes."""
    params = get_user_params(design)
    x_range = (commandState["rangeStart"], commandState["rangeEnd"])
    enabled = [curve for curve in curves if curve.get("enabled", False)]
    overrides = commandState.get("setupVarOverrides", {})
    cache_key = repr((enabled, x_range, sorted(params.items()), sorted(overrides.items()), unit_scale()))
    cached = commandState.get("analysisCache")
    if cached and cached[0] == cache_key:
        return cached[1]

    results = []
    max_abs = curve_engine.LIMITS["max_abs_value_cm"] / unit_scale()
    for curve in enabled:
        curve_for_run = dict(curve)
        variables = dict(curve.get("variables", {}))
        for var_name in variables:
            override_key = f"{curve.get('name', '')}::{var_name}"
            if override_key in overrides:
                variables[var_name] = overrides[override_key]
        curve_for_run["variables"] = variables
        results.append(curve_engine.sample_curve(curve_for_run, params, x_range, max_abs_value=max_abs))

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
        lines.append("Fix the errors above (Library tab) before creating curves.")
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
    for points in pieces:
        if len(points) < 2:
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


def add_guide_line(lines, start_point, end_point):
    if math.hypot(end_point.x - start_point.x, end_point.y - start_point.y) <= 1.0e-9:
        return
    line = lines.addByTwoPoints(start_point, end_point)
    line.isConstruction = True
    previewGuides.append(line)


def add_cross_marker(lines, center, size):
    add_guide_line(
        lines,
        adsk.core.Point3D.create(center.x - size, center.y, 0),
        adsk.core.Point3D.create(center.x + size, center.y, 0)
    )
    add_guide_line(
        lines,
        adsk.core.Point3D.create(center.x, center.y - size, 0),
        adsk.core.Point3D.create(center.x, center.y + size, 0)
    )


def draw_preview_guides(sketch, frame, samples):
    """プレビューガイドラインとマーカーを描画"""
    lines = sketch.sketchCurves.sketchLines
    start = frame["start"]
    guide_end = frame["end"]
    guide_length = frame["guideLength"]
    px, py = frame["p"]
    ux, uy = frame["u"]
    range_start = min(commandState["rangeStart"], commandState["rangeEnd"])
    range_end = max(commandState["rangeStart"], commandState["rangeEnd"])

    # x startを原点にするため、0から(range_end - range_start)の範囲を使用
    range_length = (range_end - range_start) * unit_scale()
    range_start_point = adsk.core.Point3D.create(start.x + ux * 0, start.y + uy * 0, 0)
    range_end_point = adsk.core.Point3D.create(start.x + ux * range_length, start.y + uy * range_length, 0)

    # オフセット値を効率的に計算（flatten_pointsの呼び出しを最小化）
    offsets = [0.0]
    for _, pieces in samples:
        for piece in pieces:
            for x, y, _ in piece:
                offsets.append((x - start.x) * px + (y - start.y) * py)

    if not offsets or len(offsets) == 1:
        # サンプルがない場合のフォールバック
        min_offset = 0.0
        max_offset = 0.0
    else:
        min_offset = min(offsets)
        max_offset = max(offsets)

    left_low = adsk.core.Point3D.create(range_start_point.x + px * min_offset, range_start_point.y + py * min_offset, 0)
    left_high = adsk.core.Point3D.create(range_start_point.x + px * max_offset, range_start_point.y + py * max_offset, 0)
    right_low = adsk.core.Point3D.create(range_end_point.x + px * min_offset, range_end_point.y + py * min_offset, 0)
    right_high = adsk.core.Point3D.create(range_end_point.x + px * max_offset, range_end_point.y + py * max_offset, 0)

    add_guide_line(lines, start, guide_end)
    add_guide_line(lines, range_start_point, range_end_point)
    add_guide_line(lines, left_low, right_low)
    add_guide_line(lines, left_high, right_high)
    add_guide_line(lines, left_low, left_high)
    add_guide_line(lines, right_low, right_high)

    marker_size = max(max(guide_length, range_length) * 0.03, 0.2)
    add_cross_marker(lines, start, marker_size)
    add_cross_marker(lines, guide_end, marker_size)
    add_cross_marker(lines, range_start_point, marker_size * 0.8)
    add_cross_marker(lines, range_end_point, marker_size * 0.8)

    if commandState["snapPoint"]:
        add_cross_marker(lines, commandState["snapPoint"], marker_size * 0.8)


def draw_preview(sketch, design):
    clear_preview()

    frame = build_frame()
    if not frame:
        if commandState["start"]:
            lines = sketch.sketchCurves.sketchLines
            add_cross_marker(lines, commandState["start"], 0.25)
            if commandState["snapPoint"]:
                add_cross_marker(lines, commandState["snapPoint"], 0.2)
        commandState["previewDirty"] = False
        return False

    samples = collect_curve_samples(design, frame)
    if not samples:
        draw_preview_guides(sketch, frame, [])
        commandState["previewDirty"] = False
        return False

    draw_preview_guides(sketch, frame, samples)
    for result, pieces in samples:
        try:
            add_curve_geometry(sketch, result, pieces, previewCurves)
        except:
            pass  # 失敗した曲線はプレビューしない（作成時にメッセージを出す）

    commandState["previewDirty"] = False
    return True


def create_final_curves(sketch, design):
    frame = build_frame()
    if not frame:
        return False

    samples = collect_curve_samples(design, frame)
    if not samples:
        return False

    axis_line = sketch.sketchCurves.sketchLines.addByTwoPoints(frame["start"], frame["end"])
    axis_line.isConstruction = True

    failed = []
    for result, pieces in samples:
        try:
            add_curve_geometry(sketch, result, pieces, [])
        except Exception as ex:
            failed.append(f"{result.name}: {ex}")

    if failed:
        app = adsk.core.Application.get()
        app.userInterface.messageBox(
            "Some curves could not be created in Fusion:\n" + "\n".join(failed),
            "Math Curve"
        )
    return True


def refresh_list(dropdown):
    if not dropdown:
        return
    global selectedIndex
    if not curves:
        selectedIndex = 0
        dropdown.listItems.clear()
        return
    selectedIndex = max(0, min(selectedIndex, len(curves) - 1))
    dropdown.listItems.clear()
    for index, curve in enumerate(curves):
        dropdown.listItems.add(curve["name"], index == selectedIndex)


def refresh_library_list_input(inputs):
    dropdown = adsk.core.DropDownCommandInput.cast(get_command_input(inputs, "list"))
    refresh_list(dropdown)


def refresh_curve_checkboxes(inputs):
    """Functions To Draw のテーブルを再構築"""
    setup_tab = adsk.core.TabCommandInput.cast(get_command_input(inputs, "setupTab"))
    table = adsk.core.TableCommandInput.cast(get_command_input(inputs, "curveSelectionTable"))
    if setup_tab:
        if table:
            try:
                table.deleteMe()
            except:
                pass
        table = setup_tab.children.addTableCommandInput("curveSelectionTable", "", 5, "4:1:1:1:1")
    elif not table:
        return

    stale_inputs = []
    for i in range(inputs.count):
        item = inputs.item(i)
        if not item:
            continue
        item_id = item.id
        if (
            item_id == "curveSelectionEmptyLabel"
            or item_id.startswith("curveName_")
            or item_id.startswith("curveEnabled_")
            or item_id.startswith("curveInvertOrigin_")
            or item_id.startswith("curveInvertX_")
            or item_id.startswith("curveInvertY_")
        ):
            stale_inputs.append(item)

    for stale in stale_inputs:
        try:
            stale.deleteMe()
        except:
            pass

    while table.rowCount > 0:
        try:
            table.deleteRow(0)
        except:
            break

    if not curves:
        empty_stale = get_command_input(inputs, "curveSelectionEmptyLabel")
        if empty_stale:
            try:
                empty_stale.deleteMe()
            except:
                pass
        empty_input = inputs.addStringValueInput(
            "curveSelectionEmptyLabel",
            "",
            "No saved functions yet. Create one in the Library tab."
        )
        empty_input.isReadOnly = True
        table.addCommandInput(empty_input, 0, 0, 0, 4)
        return

    for index, curve in enumerate(curves):
        try:
            name_input = inputs.addStringValueInput(
                f"curveName_{index}",
                "",
                curve.get("name", f"Curve {index + 1}")
            )
            name_input.isReadOnly = True
            draw_input = inputs.addBoolValueInput(
                f"curveEnabled_{index}",
                "Draw",
                True,
                "",
                curve.get("enabled", False)
            )
            inv_o_input = inputs.addBoolValueInput(
                f"curveInvertOrigin_{index}",
                "InvO",
                True,
                "",
                curve.get("invert_origin", False)
            )
            inv_x_input = inputs.addBoolValueInput(
                f"curveInvertX_{index}",
                "InvX",
                True,
                "",
                curve.get("invert_x", False)
            )
            inv_y_input = inputs.addBoolValueInput(
                f"curveInvertY_{index}",
                "InvY",
                True,
                "",
                curve.get("invert_y", False)
            )
            table.addCommandInput(name_input, index, 0)
            table.addCommandInput(draw_input, index, 1)
            table.addCommandInput(inv_o_input, index, 2)
            table.addCommandInput(inv_x_input, index, 3)
            table.addCommandInput(inv_y_input, index, 4)
        except Exception as ex:
            app = adsk.core.Application.get()
            if app and app.userInterface:
                app.userInterface.messageBox(f"Failed to build function row: {curve.get('name', 'Unnamed')} ({str(ex)})")
            return

    try:
        adsk.doEvents()
    except:
        pass


def refresh_setup_variables_table(inputs):
    setup_tab = adsk.core.TabCommandInput.cast(get_command_input(inputs, "setupTab"))
    table = adsk.core.TableCommandInput.cast(get_command_input(inputs, "curveVariablesTable"))
    if setup_tab:
        if table:
            try:
                table.deleteMe()
            except:
                pass
        table = setup_tab.children.addTableCommandInput("curveVariablesTable", "", 3, "3:2:2")
    elif not table:
        return

    stale_inputs = []
    for i in range(inputs.count):
        item = inputs.item(i)
        if not item:
            continue
        item_id = item.id
        if (
            item_id == "curveVariablesEmptyLabel"
            or item_id.startswith("curveVarCurve_")
            or item_id.startswith("curveVarName_")
            or item_id.startswith("curveVarValue_")
        ):
            stale_inputs.append(item)
    for stale in stale_inputs:
        try:
            stale.deleteMe()
        except:
            pass

    while table.rowCount > 0:
        try:
            table.deleteRow(0)
        except:
            break

    row = 0
    for curve_index, curve in enumerate(curves):
        variables = curve.get("variables", {})
        for var_name, default_value in variables.items():
            override_key = f"{curve.get('name', '')}::{var_name}"
            current_value = commandState.get("setupVarOverrides", {}).get(override_key, default_value)
            var_key = var_name

            curve_name_input = inputs.addStringValueInput(
                f"curveVarCurve_{curve_index}_{row}",
                "",
                curve.get("name", f"Curve {curve_index + 1}")
            )
            curve_name_input.isReadOnly = True
            var_name_input = inputs.addStringValueInput(
                f"curveVarName_{curve_index}_{row}",
                "",
                var_name
            )
            var_name_input.isReadOnly = True
            var_value_input = inputs.addValueInput(
                f"curveVarValue_{curve_index}_{var_key}",
                "",
                "",
                adsk.core.ValueInput.createByReal(current_value)
            )
            table.addCommandInput(curve_name_input, row, 0)
            table.addCommandInput(var_name_input, row, 1)
            table.addCommandInput(var_value_input, row, 2)
            row += 1

    if row == 0:
        empty_input = inputs.addStringValueInput(
            "curveVariablesEmptyLabel",
            "",
            "No variables defined. Set variables in Library using format: a=1,b=2"
        )
        empty_input.isReadOnly = True
        table.addCommandInput(empty_input, 0, 0, 0, 2)

    try:
        adsk.doEvents()
    except:
        pass


def any_curve_enabled():
    return any(curve.get("enabled", False) for curve in curves)


def select_dropdown_item(dropdown, index):
    if dropdown and 0 <= index < dropdown.listItems.count:
        item = dropdown.listItems.item(index)
        if not item.isSelected:
            item.isSelected = True


def selected_dropdown_index(inputs, input_id):
    dropdown = adsk.core.DropDownCommandInput.cast(get_command_input(inputs, input_id))
    if dropdown and dropdown.selectedItem:
        return dropdown.selectedItem.index
    return -1


def set_curve_type_state(kind):
    commandState["curveType"] = kind
    commandState["isParametricMode"] = kind != "implicit"


def load_curve_ui(inputs, is_parametric=False):
    if not curves:
        return
    curve = curves[selectedIndex]
    kind = curve_engine.curve_type(curve)
    set_curve_type_state(kind)

    name_input = adsk.core.StringValueCommandInput.cast(get_command_input(inputs, "curveNameEdit"))
    if name_input:
        name_input.value = curve.get("name", "")
    type_input = adsk.core.DropDownCommandInput.cast(get_command_input(inputs, "curveType"))
    select_dropdown_item(type_input, [k for k, _ in CURVE_TYPE_LABELS].index(kind))
    vars_input = adsk.core.StringValueCommandInput.cast(get_command_input(inputs, "variablesText"))
    if vars_input:
        vars_input.value = curve.get("variables_text", "")

    if kind == "implicit":
        expr_input = adsk.core.StringValueCommandInput.cast(get_command_input(inputs, "expr"))
        step_input = adsk.core.ValueCommandInput.cast(get_command_input(inputs, "step"))
        if expr_input:
            expr_input.value = curve.get("expr", "sin(x)")
        if step_input:
            step_input.value = curve.get("step", 0.2)
    else:
        for input_id, field, default in (("xExpr", "x_expr", "cos(t)"), ("yExpr", "y_expr", "sin(t)"),
                                         ("zExpr", "z_expr", "0")):
            target = adsk.core.StringValueCommandInput.cast(get_command_input(inputs, input_id))
            if target:
                target.value = curve.get(field, default)
        for input_id, field, default in (("tStart", "t_start", 0.0), ("tEnd", "t_end", math.pi * 2),
                                         ("tStep", "t_step", 0.1)):
            target = adsk.core.ValueCommandInput.cast(get_command_input(inputs, input_id))
            if target:
                target.value = curve.get(field, default)
        close_input = adsk.core.DropDownCommandInput.cast(get_command_input(inputs, "closeMode"))
        close_modes = [mode for mode, _ in curve_library.CLOSE_MODE_LABELS]
        close_mode = curve.get("close_mode", curve_engine.CLOSE_OPEN)
        select_dropdown_item(close_input, close_modes.index(close_mode) if close_mode in close_modes else 0)
    update_expression_status(inputs)


def save_curve_ui(inputs, is_parametric=False):
    if not curves:
        return
    curve = curves[selectedIndex]
    name_input = adsk.core.StringValueCommandInput.cast(get_command_input(inputs, "curveNameEdit"))
    if name_input:
        new_name = name_input.value.strip()
        if new_name:
            curve["name"] = new_name
    vars_input = adsk.core.StringValueCommandInput.cast(get_command_input(inputs, "variablesText"))
    if vars_input:
        curve["variables_text"] = vars_input.value
        curve["variables"] = parse_variables_text(vars_input.value)

    kind = curve_engine.curve_type(curve)
    if kind == "implicit":
        expr_input = adsk.core.StringValueCommandInput.cast(get_command_input(inputs, "expr"))
        step_input = adsk.core.ValueCommandInput.cast(get_command_input(inputs, "step"))
        if expr_input:
            curve["expr"] = expr_input.value
        if step_input:
            curve["step"] = step_input.value
    else:
        fields = [("xExpr", "x_expr"), ("yExpr", "y_expr")]
        if kind == "parametric3d":
            fields.append(("zExpr", "z_expr"))
        for input_id, field in fields:
            target = adsk.core.StringValueCommandInput.cast(get_command_input(inputs, input_id))
            if target:
                curve[field] = target.value
        for input_id, field in (("tStart", "t_start"), ("tEnd", "t_end"), ("tStep", "t_step")):
            target = adsk.core.ValueCommandInput.cast(get_command_input(inputs, input_id))
            if target:
                curve[field] = target.value
        close_index = selected_dropdown_index(inputs, "closeMode")
        if close_index >= 0:
            curve["close_mode"] = curve_library.CLOSE_MODE_LABELS[close_index][0]
    commandState["previewDirty"] = True
    update_expression_status(inputs)
    persist_library()


def persist_library():
    """Save the library after every change so it survives a Fusion restart."""
    try:
        curve_library.save_library(curve_library.default_library_path(), curves)
        if (commandState.get("notice") or "").startswith("Could not save"):
            commandState["notice"] = None
    except Exception as ex:
        commandState["notice"] = f"Could not save the function library: {ex}"


def load_saved_library():
    loaded, message = curve_library.load_library(curve_library.default_library_path())
    curves[:] = loaded or [default_curve()]
    commandState["notice"] = message


def update_expression_status(inputs):
    status_input = adsk.core.TextBoxCommandInput.cast(get_command_input(inputs, "exprStatus"))
    if not status_input or not curves:
        return
    curve = curves[selectedIndex]
    problems = curve_engine.check_curve(curve, get_user_params(get_active_design()).keys())
    status_input.text = "OK" if not problems else "\n".join(problems)


def update_status_box(inputs):
    """Refresh the Setup status text and drop a 'Draw anyway' that no longer matches the warnings."""
    report = analyze_curves(get_active_design())
    ack_input = adsk.core.BoolValueCommandInput.cast(get_command_input(inputs, "acceptWarnings"))
    if ack_input:
        has_warnings = bool(warning_signature(report))
        if ack_input.value and not warnings_acknowledged(report):
            ack_input.value = False
            commandState["ackSignature"] = None
        ack_input.isEnabled = has_warnings
    status_input = adsk.core.TextBoxCommandInput.cast(get_command_input(inputs, "drawStatus"))
    if status_input:
        status_input.text = format_report(report)


def add_preset(inputs):
    global selectedIndex
    index = selected_dropdown_index(inputs, "presetList")
    if index < 0:
        return
    curve = curve_library.curve_from_preset(curve_library.PRESETS[index])
    curve["name"] = curve_library.unique_name(curve["name"], [c["name"] for c in curves])
    curves.append(curve)
    selectedIndex = len(curves) - 1
    persist_library()


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
    global selectedIndex
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
    selectedIndex = len(curves) - 1
    persist_library()
    message = f"Imported {len(imported)} function(s)."
    if skipped:
        message += f" {skipped} unreadable function(s) were skipped."
    ui.messageBox(message, "Math Curve")


def sync_curve_selection_from_inputs(inputs):
    for index, curve in enumerate(curves):
        enabled_input = adsk.core.BoolValueCommandInput.cast(get_command_input(inputs, f"curveEnabled_{index}"))
        inv_o_input = adsk.core.BoolValueCommandInput.cast(get_command_input(inputs, f"curveInvertOrigin_{index}"))
        inv_x_input = adsk.core.BoolValueCommandInput.cast(get_command_input(inputs, f"curveInvertX_{index}"))
        inv_y_input = adsk.core.BoolValueCommandInput.cast(get_command_input(inputs, f"curveInvertY_{index}"))
        if enabled_input:
            curve["enabled"] = enabled_input.value
        if inv_o_input:
            curve["invert_origin"] = inv_o_input.value
        if inv_x_input:
            curve["invert_x"] = inv_x_input.value
        if inv_y_input:
            curve["invert_y"] = inv_y_input.value


def update_placement_inputs(inputs):
    baseline_input = adsk.core.SelectionCommandInput.cast(inputs.itemById("baselineLine"))
    start_info = adsk.core.TextBoxCommandInput.cast(inputs.itemById("startInfo"))
    end_info = adsk.core.TextBoxCommandInput.cast(inputs.itemById("endInfo"))
    snap_info = adsk.core.TextBoxCommandInput.cast(inputs.itemById("snapInfo"))
    help_info = adsk.core.TextBoxCommandInput.cast(inputs.itemById("placementHelp"))
    angle_input = adsk.core.ValueCommandInput.cast(inputs.itemById("angle"))
    length_input = adsk.core.ValueCommandInput.cast(inputs.itemById("length"))
    range_start_input = adsk.core.ValueCommandInput.cast(inputs.itemById("rangeStart"))
    range_end_input = adsk.core.ValueCommandInput.cast(inputs.itemById("rangeEnd"))

    end_point = current_end_point()

    if start_info:
        start_info.text = f"Origin: {format_point(commandState['start'])}"
    if end_info:
        end_info.text = f"Range end: {format_point(end_point)}"
    if snap_info:
        snap_info.text = f"Snap target: {format_point(commandState['snapPoint'])}"

    frame = build_frame()
    if frame and angle_input and length_input:
        angle_input.value = frame["angle"]
        length_input.value = frame["guideLength"] / unit_scale()
        angle_input.isEnabled = False
        length_input.isEnabled = False
    elif angle_input and length_input:
        angle_input.isEnabled = False
        length_input.isEnabled = False

    if range_start_input:
        range_start_input.value = commandState["rangeStart"]
    if range_end_input:
        range_end_input.value = commandState["rangeEnd"]

    if help_info:
        if not commandState["baselineToken"]:
            help_info.text = "Placement step 1: select an existing sketch line. Its start point becomes the function origin and its direction becomes the x-axis."
        else:
            help_info.text = "Placement is driven by the selected sketch line. Edit that line to change origin or direction, then reopen or refresh this command."

    if baseline_input:
        baseline_input.isEnabled = not bool(commandState["baselineToken"])


def activate_functions_tab(inputs):
    return


def update_preview(command=None, force=False):
    if not force and not commandState["previewDirty"]:
        return

    if command:
        try:
            command.doExecutePreview()
            return
        except:
            pass

    render_preview()


def is_sketch_environment_ready(ui):
    if get_active_sketch():
        return True
    ui.messageBox("Open or edit a sketch before running Math Curve Sketch.")
    return False


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


def remove_ui(remove_reload_definition=True, remove_reload_control=True):
    app = adsk.core.Application.get()
    ui = app.userInterface
    panel = ui.allToolbarPanels.itemById(PANEL_ID)
    if panel:
        delete_control_if_exists(panel, MAIN_CMD_ID)
        if remove_reload_control:
            delete_control_if_exists(panel, RELOAD_CMD_ID)

    delete_definition_if_exists(ui, MAIN_CMD_ID)
    if remove_reload_definition:
        delete_definition_if_exists(ui, RELOAD_CMD_ID)


def create_or_replace_button(panel, cmd_def):
    delete_control_if_exists(panel, cmd_def.id)
    control = panel.controls.addCommand(cmd_def)
    control.isPromoted = True
    return control


def restart_main_ui():
    global handlers
    clear_preview()
    handlers = []
    remove_ui(remove_reload_definition=False, remove_reload_control=False)

    app = adsk.core.Application.get()
    ui = app.userInterface
    panel = ui.allToolbarPanels.itemById(PANEL_ID)

    cmd_def = ui.commandDefinitions.addButtonDefinition(
        MAIN_CMD_ID,
        "Math Curve Sketch",
        "Create sketch curves from mathematical functions.",
        ICON_FOLDER
    )

    on_created = CommandCreatedHandler()
    cmd_def.commandCreated.add(on_created)
    handlers.append(on_created)

    create_or_replace_button(panel, cmd_def)

    try:
        cmd_def.execute()
        ui.messageBox("Math Curve was reloaded and reopened.")
    except:
        ui.messageBox("Math Curve buttons were rebuilt. If the command did not reopen, run Math Curve Sketch again.")


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    try:
        if not curves:
            load_saved_library()

        panel = ui.allToolbarPanels.itemById(PANEL_ID)
        delete_control_if_exists(panel, MAIN_CMD_ID)
        delete_control_if_exists(panel, RELOAD_CMD_ID)
        delete_definition_if_exists(ui, MAIN_CMD_ID)

        reload_def = ui.commandDefinitions.itemById(RELOAD_CMD_ID)
        if reload_def:
            try:
                reload_def.deleteMe()
            except:
                reload_def = ui.commandDefinitions.itemById(RELOAD_CMD_ID)

        cmd_def = ui.commandDefinitions.addButtonDefinition(
            MAIN_CMD_ID,
            "Math Curve Sketch",
            "Create sketch curves from mathematical functions.",
            ICON_FOLDER
        )

        on_created = CommandCreatedHandler()
        cmd_def.commandCreated.add(on_created)
        handlers.append(on_created)

        if not reload_def:
            reload_def = ui.commandDefinitions.addButtonDefinition(
                RELOAD_CMD_ID,
                "Reload Math Curve",
                "Recovery button for Math Curve. Rebuild the tool buttons and reopen the command.",
                get_reload_icon_folder()
            )

        on_reload = ReloadCommandCreatedHandler()
        reload_def.commandCreated.add(on_reload)
        handlers.append(on_reload)

        create_or_replace_button(panel, cmd_def)
        create_or_replace_button(panel, reload_def)
    except:
        ui.messageBox(traceback.format_exc())


def stop(context):
    global handlers
    clear_preview()
    handlers = []
    remove_ui()


class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            command = args.command
            command.isRepeatable = False
            command.okButtonText = "Create Curves"
            try:
                command.isPositionDependent = True
            except:
                pass

            reset_point_state()
            reset_curve_selection()
            commandState["unit"] = document_length_unit(get_active_design())
            commandState["ackSignature"] = None
            commandState["analysisCache"] = None

            inputs = command.commandInputs

            placement_tab = inputs.addTabCommandInput("placementTab", "Placement")
            placement_children = placement_tab.children
            placement_children.addTextBoxCommandInput(
                "placementHelp",
                "Guide",
                "Placement step 1: select an existing sketch line. Its start point becomes the function origin and its direction becomes the x-axis.",
                2,
                True
            )
            baseline_input = placement_children.addSelectionInput(
                "baselineLine",
                "Baseline Line",
                "Select an existing sketch line to define the function origin and direction."
            )
            baseline_input.addSelectionFilter("SketchLines")
            baseline_input.setSelectionLimits(0, 1)
            baseline_input.isUseCurrentSelections = False
            baseline_input.hasFocus = True
            baseline_input.commandPrompt = "Select one sketch line to use as the function baseline."
            placement_children.addTextBoxCommandInput("startInfo", "Origin", "Origin: Not set", 1, True)
            placement_children.addTextBoxCommandInput("endInfo", "Range", "Range end: Not set", 1, True)
            placement_children.addTextBoxCommandInput("snapInfo", "Snap", "Snap target: Not set", 1, True)
            placement_children.addValueInput(
                "angle",
                "Baseline Angle",
                "rad",
                adsk.core.ValueInput.createByReal(0.0)
            )
            placement_children.addValueInput(
                "length",
                "Baseline Length",
                "",
                adsk.core.ValueInput.createByReal(10.0)
            )
            placement_children.addBoolValueInput("resetRange", "Reset Placement", False, "", False)

            setup_tab = inputs.addTabCommandInput("setupTab", "Setup")
            setup_children = setup_tab.children
            setup_children.addTextBoxCommandInput(
                "setupHelp",
                "Info",
                "Configure placement and drawing range for this run. All function values use the unit below; "
                "trigonometric functions use radians.",
                2,
                True
            )
            unit_input = setup_children.addDropDownCommandInput(
                "unit",
                "Function Unit",
                adsk.core.DropDownStyles.TextListDropDownStyle
            )
            for unit in UNIT_ORDER:
                unit_input.listItems.add(f"1 = 1 {unit}", unit == commandState["unit"])
            setup_children.addValueInput(
                "rangeStart",
                "x Start",
                "",
                adsk.core.ValueInput.createByReal(commandState["rangeStart"])
            )
            setup_children.addValueInput(
                "rangeEnd",
                "x End",
                "",
                adsk.core.ValueInput.createByReal(commandState["rangeEnd"])
            )
            setup_children.addTextBoxCommandInput(
                "drawStatus",
                "Status",
                "",
                5,
                True
            )
            setup_children.addBoolValueInput("acceptWarnings", "Draw anyway", True, "", False)
            setup_children.addTextBoxCommandInput(
                "curveSelectionHelp",
                "Functions To Draw",
                "Function | Draw | InvO (origin) | InvX | InvY",
                1,
                True
            )
            setup_children.addBoolValueInput("refreshSetupFunctions", "Refresh Functions", False, "", False)
            setup_children.addTableCommandInput("curveSelectionTable", "", 5, "4:1:1:1:1")
            setup_children.addTextBoxCommandInput(
                "curveVariablesHelp",
                "Variables",
                "Function Variables (editable): Function | Variable | Value",
                1,
                True
            )
            setup_children.addTableCommandInput("curveVariablesTable", "", 3, "3:2:2")

            library_tab = inputs.addTabCommandInput("libraryTab", "Library")
            library_children = library_tab.children
            curve_list = library_children.addDropDownCommandInput(
                "list",
                "Saved Functions",
                adsk.core.DropDownStyles.TextListDropDownStyle
            )
            refresh_list(curve_list)
            library_children.addBoolValueInput("add", "Add Function", False, "", False)
            library_children.addBoolValueInput("del", "Delete Function", False, "", False)
            preset_list = library_children.addDropDownCommandInput(
                "presetList",
                "Preset Gallery",
                adsk.core.DropDownStyles.TextListDropDownStyle
            )
            for index, preset in enumerate(curve_library.PRESETS):
                preset_list.listItems.add(curve_library.preset_label(preset), index == 0)
            library_children.addBoolValueInput("addPreset", "Add Preset", False, "", False)
            library_children.addStringValueInput("curveNameEdit", "Name", "")
            type_input = library_children.addDropDownCommandInput(
                "curveType",
                "Curve Type",
                adsk.core.DropDownStyles.TextListDropDownStyle
            )
            for kind, label in CURVE_TYPE_LABELS:
                type_input.listItems.add(label, kind == commandState["curveType"])
            library_children.addStringValueInput("expr", "y =", "sin(x)")
            library_children.addStringValueInput("variablesText", "Variables", "")
            library_children.addValueInput(
                "step",
                "Step",
                "",
                adsk.core.ValueInput.createByReal(0.2)
            )
            library_children.addStringValueInput("xExpr", "x(t) =", "cos(t)")
            library_children.addStringValueInput("yExpr", "y(t) =", "sin(t)")
            library_children.addStringValueInput("zExpr", "z(t) =", "0")
            library_children.addValueInput(
                "tStart",
                "t Start",
                "",
                adsk.core.ValueInput.createByReal(0.0)
            )
            library_children.addValueInput(
                "tEnd",
                "t End",
                "",
                adsk.core.ValueInput.createByReal(math.pi * 2)
            )
            library_children.addValueInput(
                "tStep",
                "t Step",
                "",
                adsk.core.ValueInput.createByReal(0.1)
            )
            close_input = library_children.addDropDownCommandInput(
                "closeMode",
                "Start / End",
                adsk.core.DropDownStyles.TextListDropDownStyle
            )
            for index, (_, label) in enumerate(curve_library.CLOSE_MODE_LABELS):
                close_input.listItems.add(label, index == 0)
            library_children.addTextBoxCommandInput("exprStatus", "Check", "", 2, True)
            library_children.addBoolValueInput("saveCurve", "Save Changes", False, "", False)
            library_children.addBoolValueInput("exportLibrary", "Export Library...", False, "", False)
            library_children.addBoolValueInput("importLibrary", "Import Library...", False, "", False)
            library_children.addTextBoxCommandInput(
                "functionHelp",
                "Info",
                "Changes are saved automatically and restored next time. Use ^ or ** for powers "
                "(x^2). Functions: sin cos tan asin acos atan atan2 sinh cosh tanh exp log log10 sqrt "
                "cbrt abs floor ceil min max hypot sign. Variables use letters, digits, and underscores "
                "(for example: a=1,b_2=2). Fusion user parameters can be used by name.",
                4,
                True
            )

            on_input = InputChangedHandler()
            command.inputChanged.add(on_input)
            handlers.append(on_input)

            on_preview = ExecutePreviewHandler()
            command.executePreview.add(on_preview)
            handlers.append(on_preview)

            on_execute = ExecuteHandler()
            command.execute.add(on_execute)
            handlers.append(on_execute)

            on_validate = ValidateInputsHandler()
            command.validateInputs.add(on_validate)
            handlers.append(on_validate)

            on_mouse_move = MouseMoveHandler()
            command.mouseMove.add(on_mouse_move)
            handlers.append(on_mouse_move)

            on_mouse_drag = MouseDragHandler()
            command.mouseDrag.add(on_mouse_drag)
            handlers.append(on_mouse_drag)

            on_mouse_click = MouseClickHandler()
            command.mouseClick.add(on_mouse_click)
            handlers.append(on_mouse_click)

            on_destroy = DestroyHandler()
            command.destroy.add(on_destroy)
            handlers.append(on_destroy)

            load_curve_ui(inputs, is_parametric=is_parametric_mode_active())
            sync_parametric_inputs_enabled(inputs)
            refresh_curve_checkboxes(inputs)
            refresh_setup_variables_table(inputs)
            update_placement_inputs(inputs)
            update_status_box(inputs)
            update_preview(command)
        except:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(traceback.format_exc())


class ReloadExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            restart_main_ui()
        except:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(traceback.format_exc())


class ReloadCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            command = args.command
            on_execute = ReloadExecuteHandler()
            command.execute.add(on_execute)
            handlers.append(on_execute)
        except:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(traceback.format_exc())


class InputChangedHandler(adsk.core.InputChangedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        global selectedIndex

        try:
            inputs = args.inputs
            changed = args.input
            command = args.firingEvent.sender
            should_update_preview = False

            if changed.id == "list":
                selectedIndex = changed.selectedItem.index
                load_curve_ui(inputs, is_parametric=is_parametric_mode_active())
                sync_parametric_inputs_enabled(inputs)
            elif changed.id == "setupTab":
                refresh_library_list_input(inputs)
                refresh_curve_checkboxes(inputs)
                refresh_setup_variables_table(inputs)
            elif changed.id == "libraryTab":
                refresh_library_list_input(inputs)
                load_curve_ui(inputs, is_parametric=is_parametric_mode_active())
                sync_parametric_inputs_enabled(inputs)
                refresh_curve_checkboxes(inputs)
                refresh_setup_variables_table(inputs)
            elif changed.id == "refreshSetupFunctions":
                changed.value = False
                refresh_library_list_input(inputs)
                refresh_curve_checkboxes(inputs)
                refresh_setup_variables_table(inputs)
                sync_curve_selection_from_inputs(inputs)
            elif ("curveEnabled_" in changed.id) or ("curveInvert" in changed.id):
                sync_curve_selection_from_inputs(inputs)
                if "curveInvert" in changed.id:
                    persist_library()
                commandState["previewDirty"] = True
                should_update_preview = True
            elif changed.id in ("add", "addPreset"):
                changed.value = False
                if changed.id == "add":
                    curves.append(new_curve_of_type(commandState.get("curveType", "implicit")))
                    selectedIndex = len(curves) - 1
                    persist_library()
                else:
                    add_preset(inputs)
                refresh_library_list_input(inputs)
                load_curve_ui(inputs, is_parametric=is_parametric_mode_active())
                sync_parametric_inputs_enabled(inputs)
                refresh_curve_checkboxes(inputs)
                refresh_setup_variables_table(inputs)
                sync_curve_selection_from_inputs(inputs)
            elif changed.id == "del":
                if len(curves) > 1:
                    curves.pop(selectedIndex)
                    persist_library()
                changed.value = False
                selectedIndex = min(selectedIndex, len(curves) - 1)
                refresh_library_list_input(inputs)
                load_curve_ui(inputs, is_parametric=is_parametric_mode_active())
                sync_parametric_inputs_enabled(inputs)
                refresh_curve_checkboxes(inputs)
                refresh_setup_variables_table(inputs)
                sync_curve_selection_from_inputs(inputs)
                commandState["previewDirty"] = True
                should_update_preview = True
            elif changed.id == "expr" or changed.id == "step" or changed.id == "variablesText":
                save_curve_ui(inputs)
                refresh_library_list_input(inputs)
                refresh_curve_checkboxes(inputs)
                refresh_setup_variables_table(inputs)
                should_update_preview = True
            elif changed.id in ("xExpr", "yExpr", "zExpr", "tStart", "tEnd", "tStep", "closeMode"):
                save_curve_ui(inputs)
                refresh_library_list_input(inputs)
                refresh_curve_checkboxes(inputs)
                should_update_preview = True
            elif changed.id == "curveType":
                kind = CURVE_TYPE_LABELS[max(0, selected_dropdown_index(inputs, "curveType"))][0]
                set_curve_type_state(kind)
                curve = curves[selectedIndex]
                if curve_engine.curve_type(curve) != kind:
                    curve["type"] = kind
                    template = new_curve_of_type(kind)
                    for key, value in template.items():
                        if key not in ("name", "enabled"):
                            curve.setdefault(key, value)
                    persist_library()
                    commandState["previewDirty"] = True
                    should_update_preview = True
                sync_parametric_inputs_enabled(inputs)
                load_curve_ui(inputs, is_parametric=is_parametric_mode_active())
                refresh_library_list_input(inputs)
                refresh_curve_checkboxes(inputs)
                refresh_setup_variables_table(inputs)
            elif changed.id in ("exportLibrary", "importLibrary"):
                changed.value = False
                if changed.id == "exportLibrary":
                    export_library()
                else:
                    import_library()
                    refresh_library_list_input(inputs)
                    load_curve_ui(inputs, is_parametric=is_parametric_mode_active())
                    sync_parametric_inputs_enabled(inputs)
                    refresh_curve_checkboxes(inputs)
                    refresh_setup_variables_table(inputs)
            elif changed.id == "unit":
                index = selected_dropdown_index(inputs, "unit")
                if index >= 0:
                    commandState["unit"] = UNIT_ORDER[index]
                commandState["previewDirty"] = True
                should_update_preview = True
            elif changed.id == "acceptWarnings":
                report = analyze_curves(get_active_design())
                commandState["ackSignature"] = warning_signature(report) if changed.value else None
                commandState["previewDirty"] = True
                should_update_preview = True
            elif changed.id == "curveNameEdit":
                save_curve_ui(inputs)
                refresh_library_list_input(inputs)
                refresh_curve_checkboxes(inputs)
                refresh_setup_variables_table(inputs)
            elif changed.id == "saveCurve":
                changed.value = False
                save_curve_ui(inputs)
                refresh_library_list_input(inputs)
                refresh_curve_checkboxes(inputs)
                refresh_setup_variables_table(inputs)
                sync_curve_selection_from_inputs(inputs)
                commandState["previewDirty"] = True
                should_update_preview = True
            elif changed.id.startswith("curveVarValue_"):
                parts = changed.id.split("_")
                if len(parts) >= 3:
                    curve_index = int(parts[1])
                    var_name = "_".join(parts[2:])
                    curve = curves[curve_index] if 0 <= curve_index < len(curves) else None
                    if curve:
                        var_input = adsk.core.ValueCommandInput.cast(changed)
                        if var_input and var_name in curve.get("variables", {}):
                            key = f"{curve.get('name', '')}::{var_name}"
                            commandState["setupVarOverrides"][key] = var_input.value
                            commandState["previewDirty"] = True
                            should_update_preview = True
            elif changed.id == "baselineLine":
                baseline = get_selected_baseline(inputs)
                if baseline:
                    update_state_from_baseline(baseline)
                    selection_input = adsk.core.SelectionCommandInput.cast(inputs.itemById("baselineLine"))
                    if selection_input:
                        selection_input.hasFocus = False
                    should_update_preview = True
                else:
                    reset_point_state()
                    should_update_preview = True
            elif changed.id == "rangeStart" or changed.id == "rangeEnd":
                commandState["rangeStart"] = adsk.core.ValueCommandInput.cast(inputs.itemById("rangeStart")).value
                commandState["rangeEnd"] = adsk.core.ValueCommandInput.cast(inputs.itemById("rangeEnd")).value
                commandState["previewDirty"] = True
                should_update_preview = True
            elif changed.id == "resetRange":
                changed.value = False
                reset_point_state()
                selection_input = adsk.core.SelectionCommandInput.cast(inputs.itemById("baselineLine"))
                if selection_input:
                    selection_input.clearSelection()
                    selection_input.hasFocus = True
                should_update_preview = True
            update_placement_inputs(inputs)
            update_status_box(inputs)
            if should_update_preview:
                update_preview(command)
        except:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(traceback.format_exc())


class MouseMoveHandler(adsk.core.MouseEventHandler):
    """マウス移動イベント - 現在は使用されていない"""
    def __init__(self):
        super().__init__()

    def notify(self, args):
        # 機能未実装。将来の拡張用に残す
        pass


class MouseDragHandler(adsk.core.MouseEventHandler):
    """マウスドラッグイベント - 現在は使用されていない"""
    def __init__(self):
        super().__init__()

    def notify(self, args):
        # 機能未実装。将来の拡張用に残す
        pass


class MouseClickHandler(adsk.core.MouseEventHandler):
    """マウスクリックイベント - 現在は使用されていない"""
    def __init__(self):
        super().__init__()

    def notify(self, args):
        # 機能未実装。将来の拡張用に残す
        pass


class ValidateInputsHandler(adsk.core.ValidateInputsEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            baseline = get_baseline_from_token()
            if baseline and baseline.isValid:
                update_state_from_baseline(baseline)
            sync_curve_selection_from_inputs(args.inputs)
            args.areInputsValid = (
                range_is_final()
                and any_curve_enabled()
                and not report_blocks_creation(analyze_curves(get_active_design()))
            )
        except:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(traceback.format_exc())


class ExecutePreviewHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            sketch = get_active_sketch()
            design = get_active_design()
            if not sketch or not commandState["previewDirty"]:
                return

            draw_preview(sketch, design)
            args.isValidResult = False
        except:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(traceback.format_exc())


class ExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            app = adsk.core.Application.get()
            sketch = get_active_sketch()
            design = get_active_design()
            if not sketch or not range_is_final():
                if not sketch:
                    app.userInterface.messageBox("Open or edit a sketch before running Math Curve Sketch.")
                return
            license_status = check_license(app)
            licenseState["checked"] = True
            licenseState["allowed"] = license_status.allowed
            licenseState["mode"] = license_status.mode
            licenseState["message"] = license_status.message
            if not license_status.allowed:
                app.userInterface.messageBox(license_status.message, "Math Curve License")
                return

            report = analyze_curves(design)
            if report_blocks_creation(report):
                app.userInterface.messageBox(format_report(report), "Math Curve")
                return

            clear_preview()
            if not create_final_curves(sketch, design):
                app.userInterface.messageBox(
                    "No curve could be created. Check the selected functions, variable values, and sampling range.",
                    "Math Curve",
                )
        except:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(traceback.format_exc())


class DestroyHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            clear_preview()
            reset_point_state()
        except:
            pass

import adsk.core
import adsk.fusion
import traceback
import math
import os

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
    "invertY": False
}


def default_curve():
    return {
        "name": f"Curve {len(curves) + 1}",
        "expr": "sin(x)",
        "step": 0.2,
        "enabled": False
    }


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


def get_user_params(design):
    params = {}
    if not design:
        return params

    for p in design.userParameters:
        params[p.name] = p.value
    return params


def safe_eval(expr, val, params):
    """数式を安全に評価。エラーと数学的に無効な値をハンドリング"""
    try:
        scope = {
            "x": val,
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
            "exp": math.exp,
            "sqrt": math.sqrt,
            "log": math.log,
            "log10": math.log10,
            "fabs": math.fabs,
            "floor": math.floor,
            "ceil": math.ceil,
            "pow": math.pow,
            "pi": math.pi,
            "e": math.e
        }
        scope.update(params)
        result = eval(expr, {"__builtins__": None}, scope)
        
        # 戻り値が数値かどうか確認
        if not isinstance(result, (int, float)):
            return None
        
        # NaNや無限大をフィルタリング
        if math.isnan(result) or math.isinf(result):
            return None
            
        return result
    except ZeroDivisionError:
        return None  # ゼロ除算
    except ValueError:
        return None  # sqrt(-1)等の数学的エラー
    except Exception:
        return None  # その他の予期しないエラー


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


def collect_curve_samples(design, frame):
    """曲線のサンプルポイントを収集。浮動小数点精度を考慮してカウンター方式を使用"""
    params = get_user_params(design)
    samples = []
    range_start = min(commandState["rangeStart"], commandState["rangeEnd"])
    range_end = max(commandState["rangeStart"], commandState["rangeEnd"])

    for curve in curves:
        if not curve.get("enabled", False):
            continue

        pts = adsk.core.ObjectCollection.create()
        step = curve["step"]
        if step is None or step <= 0:
            continue

        start = frame["start"]
        ux, uy = frame["u"]
        px, py = frame["p"]

        # 浮動小数点精度問題を回避するためカウンター方式を使用
        num_steps = max(1, int(round((range_end - range_start) / step)) + 1)
        for i in range(num_steps):
            x = range_start + i * step
            if x > range_end + 1.0e-9:
                break
            
            try:
                y = safe_eval(curve["expr"], x, params)
                if y is None or not isinstance(y, (int, float)):
                    continue
                # 数学的に無効な値をチェック
                if math.isnan(y) or math.isinf(y):
                    continue
                    
                # x startを原点にするため、xからrange_startを減算
                pts.add(adsk.core.Point3D.create(
                    start.x + ux * (x - range_start) + px * y,
                    start.y + uy * (x - range_start) + py * y,
                    0
                ))
            except:
                continue  # 個別ポイント計算の失敗は無視

        if pts.count < 2:
            # エンドポイントが不足していればフォールバック
            for x in (range_start, range_end):
                try:
                    y = safe_eval(curve["expr"], x, params)
                    if y is not None and isinstance(y, (int, float)) and not math.isnan(y) and not math.isinf(y):
                        # x startを原点にするため、xからrange_startを減算
                        pts.add(adsk.core.Point3D.create(
                            start.x + ux * (x - range_start) + px * y,
                            start.y + uy * (x - range_start) + py * y,
                            0
                        ))
                except:
                    continue

        if pts.count > 1:
            samples.append(pts)

    return samples


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


def flatten_points(samples):
    points = []
    for pts in samples:
        for index in range(pts.count):
            points.append(adsk.core.Point3D.cast(pts.item(index)))
    return points


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
    range_length = range_end - range_start
    range_start_point = adsk.core.Point3D.create(start.x + ux * 0, start.y + uy * 0, 0)
    range_end_point = adsk.core.Point3D.create(start.x + ux * range_length, start.y + uy * range_length, 0)

    # オフセット値を効率的に計算（flatten_pointsの呼び出しを最小化）
    offsets = [0.0]
    try:
        for pts in samples:
            for index in range(pts.count):
                point = adsk.core.Point3D.cast(pts.item(index))
                offsets.append((point.x - start.x) * px + (point.y - start.y) * py)
    except:
        pass  # ポイント取得の失敗は無視

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

    marker_size = max(max(guide_length, range_end - range_start) * 0.03, 0.2)
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
    for pts in samples:
        spline = sketch.sketchCurves.sketchFittedSplines.add(pts)
        previewCurves.append(spline)

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

    for pts in samples:
        sketch.sketchCurves.sketchFittedSplines.add(pts)

    return True


def refresh_list(dropdown):
    dropdown.listItems.clear()
    for index, curve in enumerate(curves):
        dropdown.listItems.add(curve["name"], index == selectedIndex)


def refresh_curve_checkboxes(inputs):
    """保存済み関数のチェックボックス一覧をリフレッシュ"""
    selection_group = adsk.core.GroupCommandInput.cast(inputs.itemById("curveSelectionGroup"))
    if not selection_group:
        return

    children = selection_group.children
    stale_inputs = []
    
    # 古い入力を収集（削除前に全て収集）
    for index in range(children.count):
        child = children.item(index)
        if child.id.startswith("curveEnabled_") or child.id == "curveSelectionEmpty":
            stale_inputs.append(child)

    # 古い入力を削除
    for child in stale_inputs:
        try:
            child.deleteMe()
        except:
            pass  # 既に削除された可能性

    if not curves:
        children.addTextBoxCommandInput(
            "curveSelectionEmpty",
            "Saved Functions",
            "No saved functions yet. Create one in the Library tab.",
            2,
            True
        )
        return

    # 新規チェックボックスを追加
    for index, curve in enumerate(curves):
        try:
            children.addBoolValueInput(
                f"curveEnabled_{index}",
                curve["name"],
                True,
                "",
                curve.get("enabled", False)
            )
        except:
            pass

    selection_group.isExpanded = True
    # UIの再描画が必要な場合のみ実行
    try:
        selection_group.isVisible = False
        selection_group.isVisible = True
        adsk.doEvents()
    except:
        pass  # UIイベント処理の失敗は無視


def any_curve_enabled():
    return any(curve.get("enabled", False) for curve in curves)


def load_curve_ui(inputs):
    curve = curves[selectedIndex]
    inputs.itemById("expr").value = curve["expr"]
    inputs.itemById("step").value = curve["step"]


def save_curve_ui(inputs):
    curve = curves[selectedIndex]
    curve["expr"] = inputs.itemById("expr").value
    curve["step"] = inputs.itemById("step").value
    commandState["previewDirty"] = True


def sync_curve_selection_from_inputs(inputs):
    for index, curve in enumerate(curves):
        bool_input = adsk.core.BoolValueCommandInput.cast(inputs.itemById(f"curveEnabled_{index}"))
        if bool_input:
            curve["enabled"] = bool_input.value


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
        length_input.value = frame["guideLength"]
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


def update_preview(command=None):
    baseline = get_baseline_from_token()
    if baseline and baseline.isValid:
        update_state_from_baseline(baseline)
    commandState["previewDirty"] = True
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
        if not is_sketch_environment_ready(ui):
            return

        if not curves:
            curves.append(default_curve())

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
                "Angle",
                "rad",
                adsk.core.ValueInput.createByReal(0.0)
            )
            placement_children.addValueInput(
                "length",
                "Length",
                "",
                adsk.core.ValueInput.createByReal(10.0)
            )
            placement_children.addBoolValueInput("resetRange", "Reset Placement", False, "", False)

            setup_tab = inputs.addTabCommandInput("setupTab", "Setup")
            setup_children = setup_tab.children
            setup_children.addTextBoxCommandInput(
                "setupHelp",
                "Info",
                "Choose which saved functions to use for this run. Saved functions persist, but start unchecked each time.",
                2,
                True
            )
            setup_children.addValueInput(
                "rangeStart",
                "x Start",
                "",
                adsk.core.ValueInput.createByReal(0.0)
            )
            setup_children.addValueInput(
                "rangeEnd",
                "x End",
                "",
                adsk.core.ValueInput.createByReal(10.0)
            )
            setup_children.addBoolValueInput("invertOrigin", "Invert Origin", False, "", False)
            setup_children.addBoolValueInput("invertX", "Invert X Axis", False, "", False)
            setup_children.addBoolValueInput("invertY", "Invert Y Axis", False, "", False)
            setup_children.addGroupCommandInput("curveSelectionGroup", "Functions To Draw")

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
            library_children.addStringValueInput("expr", "y =", "sin(x)")
            library_children.addValueInput(
                "step",
                "Step",
                "",
                adsk.core.ValueInput.createByReal(0.2)
            )
            library_children.addTextBoxCommandInput(
                "functionHelp",
                "Info",
                "Create and edit saved functions here. They remain stored while the add-in stays loaded, but each new run starts with all functions unchecked.",
                2,
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

            load_curve_ui(inputs)
            refresh_curve_checkboxes(inputs)
            update_placement_inputs(inputs)
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

            if changed.id == "list":
                selectedIndex = changed.selectedItem.index
                load_curve_ui(inputs)
            elif changed.id.startswith("curveEnabled_"):
                sync_curve_selection_from_inputs(inputs)
                commandState["previewDirty"] = True
            elif changed.id == "add":
                curves.append(default_curve())
                changed.value = False
                selectedIndex = len(curves) - 1
                refresh_list(inputs.itemById("list"))
                load_curve_ui(inputs)
                refresh_curve_checkboxes(inputs)
                sync_curve_selection_from_inputs(inputs)
            elif changed.id == "del":
                if len(curves) > 1:
                    curves.pop(selectedIndex)
                changed.value = False
                selectedIndex = min(selectedIndex, len(curves) - 1)
                refresh_list(inputs.itemById("list"))
                load_curve_ui(inputs)
                refresh_curve_checkboxes(inputs)
                sync_curve_selection_from_inputs(inputs)
            elif changed.id == "expr" or changed.id == "step":
                save_curve_ui(inputs)
            elif changed.id == "baselineLine":
                baseline = get_selected_baseline(inputs)
                if baseline:
                    update_state_from_baseline(baseline)
                    selection_input = adsk.core.SelectionCommandInput.cast(inputs.itemById("baselineLine"))
                    if selection_input:
                        selection_input.hasFocus = False
                else:
                    reset_point_state()
            elif changed.id == "rangeStart" or changed.id == "rangeEnd":
                commandState["rangeStart"] = adsk.core.ValueCommandInput.cast(inputs.itemById("rangeStart")).value
                commandState["rangeEnd"] = adsk.core.ValueCommandInput.cast(inputs.itemById("rangeEnd")).value
                commandState["previewDirty"] = True
            elif changed.id == "invertOrigin":
                commandState["invertOrigin"] = changed.value
                commandState["previewDirty"] = True
            elif changed.id == "invertX":
                commandState["invertX"] = changed.value
                commandState["previewDirty"] = True
            elif changed.id == "invertY":
                commandState["invertY"] = changed.value
                commandState["previewDirty"] = True
            elif changed.id == "resetRange":
                changed.value = False
                reset_point_state()
                selection_input = adsk.core.SelectionCommandInput.cast(inputs.itemById("baselineLine"))
                if selection_input:
                    selection_input.clearSelection()
                    selection_input.hasFocus = True
            update_placement_inputs(inputs)
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
            args.areInputsValid = range_is_final() and any_curve_enabled()
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
            sketch = get_active_sketch()
            design = get_active_design()
            if not sketch or not range_is_final():
                return

            clear_preview()
            create_final_curves(sketch, design)
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

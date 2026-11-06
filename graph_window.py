"""The Math Curve window: an HTML palette with the function list, editor, graph, and placement.

The palette (resources/graph) only draws and sends requests. Sampling and library edits are
handled by graph_data; placement, viewport preview, and curve creation by math_curve_2,
connected through the hooks given to configure().
"""

import json
import os
import traceback

import adsk.core

from . import graph_data

PALETTE_ID = "MathCurvePalette"
OLD_PALETTE_IDS = ("MathCurveGraphPalette",)
PALETTE_NAME = "Math Curve"
HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "graph", "index.html")

LIBRARY_ACTIONS = ("graphData", "graphEdit", "graphAdd", "graphDelete")
SKETCH_ACTIONS = ("mcSelectLine", "mcUseOrigin", "mcClearPlacement", "mcCreate", "mcExport", "mcImport")

_handlers = []
_hooks = {}


def configure(**hooks):
    """Connect the window to the add-in.

    get_curves(), get_params(), new_curve(kind), on_saved(): the function library.
    apply_settings(settings): unit, x range, output, preview, Draw anyway from the window.
    window_state(): placement and status sent with every reply.
    on_action(action, data): Fusion-side actions; returns extra reply fields.
    on_closed(): the window was closed.
    """
    _hooks.update(hooks)


def _ui():
    return adsk.core.Application.get().userInterface


def show():
    ui = _ui()
    for old_id in OLD_PALETTE_IDS:
        old = ui.palettes.itemById(old_id)
        if old:
            old.deleteMe()
    palette = ui.palettes.itemById(PALETTE_ID)
    if not palette:
        palette = ui.palettes.add(
            PALETTE_ID,
            PALETTE_NAME,
            HTML_PATH.replace("\\", "/"),
            True,   # isVisible
            True,   # showCloseButton
            True,   # isResizable
            1040,
            680,
            True    # useNewWebBrowser
        )
        try:
            palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateFloating
        except:
            pass
        on_incoming = IncomingHandler()
        palette.incomingFromHTML.add(on_incoming)
        _handlers.append(on_incoming)
        on_closed = ClosedHandler()
        palette.closed.add(on_closed)
        _handlers.append(on_closed)
    else:
        palette.isVisible = True
        notify_library_changed()


def notify_library_changed():
    """Ask the open window to reload (library or sketch changed outside the window)."""
    try:
        palette = _ui().palettes.itemById(PALETTE_ID)
        if palette and palette.isVisible:
            palette.sendInfoToHTML("refresh", "")
    except:
        pass


def stop():
    try:
        palette = _ui().palettes.itemById(PALETTE_ID)
        if palette:
            palette.deleteMe()
    except:
        pass
    _handlers.clear()


def handle(action, data):
    """Answer one request from the window. Returns the reply dict."""
    _hooks["apply_settings"](data.get("settings"))
    curves = _hooks["get_curves"]()
    params = _hooks["get_params"]()
    extra = {}
    if action in SKETCH_ACTIONS:
        extra = _hooks["on_action"](action, data) or {}
        action = "graphData"
    reply, saved = graph_data.handle_request(action, data, curves, params, _hooks["new_curve"])
    if saved:
        _hooks["on_saved"]()
    reply.update(extra)
    reply["sketch"] = _hooks["window_state"]()
    return reply


class IncomingHandler(adsk.core.HTMLEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        html_args = adsk.core.HTMLEventArgs.cast(args)
        try:
            if html_args.action not in LIBRARY_ACTIONS + SKETCH_ACTIONS:
                return
            data = json.loads(html_args.data) if html_args.data else {}
            html_args.returnData = json.dumps(handle(html_args.action, data if isinstance(data, dict) else {}))
        except Exception:
            html_args.returnData = json.dumps({"error": "Math Curve error: " + traceback.format_exc(limit=2)})


class ClosedHandler(adsk.core.UserInterfaceGeneralEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            _hooks["on_closed"]()
        except:
            pass

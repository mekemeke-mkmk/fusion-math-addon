"""Graph window: an HTML palette that plots the function library (Desmos-like preview).

The palette (resources/graph) only draws. Sampling and edits are handled in Python by
graph_data, with the same engine that creates the sketch curves, so the graph shows what
Create Curves will draw.
"""

import json
import os
import traceback

import adsk.core

from . import graph_data

PALETTE_ID = "MathCurveGraphPalette"
PALETTE_NAME = "Math Curve Graph"
HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "graph", "index.html")

_handlers = []
_hooks = {}


def configure(get_curves, get_params, new_curve, on_saved, on_create):
    """Connect the window to the add-in's library.

    get_curves(): the live list of curve dicts. get_params(): {name: value}.
    new_curve(kind): a new default curve. on_saved(): write the library to disk.
    on_create(request): start placing curves in the sketch; returns (message, error).
    """
    _hooks.update(get_curves=get_curves, get_params=get_params, new_curve=new_curve, on_saved=on_saved,
                  on_create=on_create)


def _palette():
    ui = adsk.core.Application.get().userInterface
    return ui.palettes.itemById(PALETTE_ID)


def show():
    ui = adsk.core.Application.get().userInterface
    palette = _palette()
    if not palette:
        palette = ui.palettes.add(
            PALETTE_ID,
            PALETTE_NAME,
            HTML_PATH.replace("\\", "/"),
            True,   # isVisible
            True,   # showCloseButton
            True,   # isResizable
            900,
            560,
            True    # useNewWebBrowser
        )
        try:
            palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateFloating
        except:
            pass
        on_incoming = IncomingHandler()
        palette.incomingFromHTML.add(on_incoming)
        _handlers.append(on_incoming)
    else:
        palette.isVisible = True
        notify_library_changed()


def notify_library_changed():
    """Ask an open graph window to reload (after edits in the Math Curve dialog)."""
    try:
        palette = _palette()
        if palette and palette.isVisible:
            palette.sendInfoToHTML("refresh", "")
    except:
        pass


def stop():
    try:
        palette = _palette()
        if palette:
            palette.deleteMe()
    except:
        pass
    _handlers.clear()


class IncomingHandler(adsk.core.HTMLEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        html_args = adsk.core.HTMLEventArgs.cast(args)
        try:
            if html_args.action not in ("graphData", "graphEdit", "graphAdd", "graphDelete", "graphCreate"):
                return
            data = json.loads(html_args.data) if html_args.data else {}
            if html_args.action == "graphCreate":
                message, error = _hooks["on_create"](data)
                html_args.returnData = json.dumps({"error": error} if error else {"created": message})
                return
            reply, saved = graph_data.handle_request(
                html_args.action,
                data,
                _hooks["get_curves"](),
                _hooks["get_params"](),
                _hooks["new_curve"]
            )
            if saved:
                _hooks["on_saved"]()
            html_args.returnData = json.dumps(reply)
        except Exception:
            html_args.returnData = json.dumps({"error": "Graph error: " + traceback.format_exc(limit=2)})

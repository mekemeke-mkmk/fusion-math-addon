"""Preview of the curves in the Fusion viewport, drawn as custom graphics.

Custom graphics are display-only: they add nothing to the sketch, the timeline, or undo,
and Fusion does not solve them or look for profiles. That keeps the preview fast no
matter how many curves the sketch already has.
"""

import adsk.core
import adsk.fusion

_state = {"group": None}

GUIDE_COLOR = (140, 149, 159)


def _hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def sketch_to_model(sketch):
    """Return a function mapping sketch (x, y, z) to model coordinates for this sketch."""
    origin = sketch.sketchToModelSpace(adsk.core.Point3D.create(0, 0, 0))
    axes = []
    for x, y, z in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        p = sketch.sketchToModelSpace(adsk.core.Point3D.create(x, y, z))
        axes.append((p.x - origin.x, p.y - origin.y, p.z - origin.z))
    ox, oy, oz = origin.x, origin.y, origin.z
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = axes

    def convert(point):
        x, y, z = point
        return (ox + x * ax + y * bx + z * cx, oy + x * ay + y * by + z * cy, oz + x * az + y * bz + z * cz)
    return convert


def clear():
    group = _state.get("group")
    _state["group"] = None
    try:
        if group and group.isValid:
            group.deleteMe()
    except:
        pass
    _refresh()


def _refresh():
    try:
        viewport = adsk.core.Application.get().activeViewport
        if viewport:
            viewport.refresh()
    except:
        pass


def _add_strips(group, strips, rgb, weight):
    coordinates = []
    lengths = []
    for strip in strips:
        if len(strip) < 2:
            continue
        for point in strip:
            coordinates.extend(point)
        lengths.append(len(strip))
    if not lengths:
        return
    lines = group.addLines(
        adsk.fusion.CustomGraphicsCoordinates.create(coordinates), [], True, lengths
    )
    lines.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(*rgb, 255))
    lines.weight = weight
    try:
        lines.depthPriority = 1
    except:
        pass


def show(design, sketch, curves, guides):
    """Draw the preview.

    curves: [(hex_color, [[(x, y, z), ...], ...]), ...] in sketch coordinates.
    guides: [[(x, y, z), ...], ...] construction-like lines (baseline, x range), sketch coordinates.
    """
    clear()
    if not design or not sketch:
        return
    convert = sketch_to_model(sketch)
    group = design.rootComponent.customGraphicsGroups.add()
    _state["group"] = group
    _add_strips(group, [[convert(p) for p in strip] for strip in guides], GUIDE_COLOR, 1)
    for color, strips in curves:
        _add_strips(group, [[convert(p) for p in strip] for strip in strips], _hex_to_rgb(color), 2)
    _refresh()

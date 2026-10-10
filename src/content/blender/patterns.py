"""What transitions share, built from the `Canvas` verbs: polar coordinates, turning, zooming,
mirrored segments, soft steps, and the infinite inward spiral. Each transition is a short
choice of these; none repeats them."""

import math

from content.blender.canvas_api import Canvas, Socket, Value


def smoothstep(canvas: Canvas, low: Value, high: Value, x: Value) -> Socket:
    """0 below `low`, 1 above `high`, a smooth S between."""
    span = canvas.math("subtract", high, low)
    t = canvas.math("divide", canvas.math("subtract", x, low), span)
    t = canvas.math("minimum", canvas.math("maximum", t, 0.0), 1.0)
    # t² (3 − 2t)
    return canvas.math(
        "multiply",
        canvas.math("multiply", t, t),
        canvas.math("subtract", 3.0, canvas.math("multiply", t, 2.0)),
    )


def blend(canvas: Canvas, a: Value, b: Value, t: Value) -> Socket:
    """A number between `a` and `b`, `t` of the way."""
    return canvas.math("add", a, canvas.math("multiply", canvas.math("subtract", b, a), t))


def bump(canvas: Canvas, t: Socket) -> Socket:
    """0 at the start and the end, 1 in the middle: how strong an effect is mid-transition."""
    return canvas.math("sine", canvas.math("multiply", t, math.pi))


def polar(canvas: Canvas, at: Socket) -> tuple[Socket, Socket]:
    """A position's distance from the centre and its angle (radians)."""
    x, y = canvas.parts(at)
    radius = canvas.math(
        "sqrt", canvas.math("add", canvas.math("multiply", x, x), canvas.math("multiply", y, y))
    )
    return radius, canvas.math("arctan2", y, x)


def from_polar(canvas: Canvas, radius: Value, angle: Value) -> Socket:
    return canvas.point(
        canvas.math("multiply", radius, canvas.math("cosine", angle)),
        canvas.math("multiply", radius, canvas.math("sine", angle)),
    )


def turn(canvas: Canvas, at: Socket, angle: Value) -> Socket:
    """A position turned about the centre."""
    radius, current = polar(canvas, at)
    return from_polar(canvas, radius, canvas.math("add", current, angle))


def zoom(canvas: Canvas, at: Socket, factor: Value) -> Socket:
    """Looking `factor` times closer: positions shrink towards the centre."""
    x, y = canvas.parts(at)
    return canvas.point(canvas.math("divide", x, factor), canvas.math("divide", y, factor))


def mirrored(canvas: Canvas, at: Socket, segments: int, angle: Value) -> Socket:
    """A kaleidoscope: the frame folded into `segments` mirrored wedges, turned by `angle`."""
    radius, current = polar(canvas, at)
    wedge = 2 * math.pi / segments
    within = canvas.math(
        "modulo", canvas.math("add", canvas.math("add", current, angle), 100 * wedge), wedge
    )
    folded = canvas.math("absolute", canvas.math("subtract", within, wedge / 2))
    return from_polar(canvas, radius, folded)


def spiral(
    canvas: Canvas, at: Socket, travel: Value, *, period: float, reach: float, twist: int = 1
) -> tuple[Socket, Socket]:
    """The infinite inward spiral (the Droste effect): the frame filled with nested copies of
    a picture, each `period` times smaller than the one around it, wound into `twist` arms,
    flowing inward and turning as `travel` (in rings) grows. Each copy shows the picture out
    to `reach` from its centre, where its subject is.

    Returns where to look in the picture, and which ring a point is in: rings are numbered
    outward, and a ring keeps its number as it flows in, so new numbers arrive at the edge."""
    radius, angle = polar(canvas, at)
    log_radius = canvas.math("logarithm", canvas.math("maximum", radius, 1e-4), math.e)
    step = math.log(period)
    # Each turn round the centre moves `twist` rings: the arms join up seamlessly.
    wound = canvas.math(
        "add", log_radius, canvas.math("multiply", angle, twist * step / (2 * math.pi))
    )
    flowing = canvas.math("add", wound, canvas.math("multiply", travel, step))
    ring = canvas.math("floor", canvas.math("divide", flowing, step))
    within = canvas.math("subtract", flowing, canvas.math("multiply", ring, step))
    look = from_polar(
        canvas,
        canvas.math(
            "multiply", canvas.math("exponent", canvas.math("subtract", within, step)), reach
        ),
        angle,
    )
    return look, ring

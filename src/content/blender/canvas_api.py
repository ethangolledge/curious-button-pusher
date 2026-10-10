"""`Canvas`: everything a transition may do. A transition turns one picture into the next over a
few seconds by working out, for every point of the frame, which picture to show and where in
it to look: it is a small program on the frame, written with these verbs. `canvas.py` builds
it as a Blender shader (so it renders on the GPU); tests use a stand-in that records it.

Coordinates are centred on the frame: x runs from −aspect/2 to aspect/2, y from −0.5 to 0.5,
so a circle is round whatever the frame's shape."""

from typing import Literal, Protocol

Picture = Literal["from", "to"]
# How a picture is continued beyond its edges when it is looked at outside them.
Edge = Literal["extend", "mirror", "repeat"]
Operation = Literal[
    "add", "subtract", "multiply", "divide", "power", "logarithm", "sqrt", "absolute",
    "minimum", "maximum", "less_than", "greater_than", "sine", "cosine", "arctan2",
    "fraction", "floor", "modulo", "smooth_minimum", "exponent",
]  # fmt: skip


class Socket(Protocol):
    """A value worked out for every point of the frame (a number, a point or a colour)."""


Value = Socket | float


class Canvas(Protocol):
    @property
    def aspect(self) -> float:
        """Width over height."""
        ...

    @property
    def seconds(self) -> float:
        """How long the transition lasts."""
        ...

    def progress(self, ease: str = "in_out") -> Socket:
        """How far through the transition, from 0 to 1, eased."""
        ...

    def coords(self) -> Socket:
        """Each point's centred position (x, y)."""
        ...

    def picture(self, which: Picture, at: Socket, edge: Edge = "extend") -> Socket:
        """The colour of a picture at a position (centred coordinates of that picture)."""
        ...

    def math(self, operation: Operation, a: Value, b: Value = 0.0) -> Socket: ...

    def point(self, x: Value, y: Value) -> Socket:
        """A position from its two parts."""
        ...

    def parts(self, point: Socket) -> tuple[Socket, Socket]:
        """A position's x and y."""
        ...

    def noise(self, at: Socket, scale: Value, detail: float = 2.0) -> Socket:
        """Smooth, cloud-like noise from 0 to 1, the same for the same position."""
        ...

    def mix(self, first: Socket, second: Socket, amount: Value) -> Socket:
        """Two colours mixed: none of the second at 0, all of it at 1."""
        ...

    def colour(self, hex_colour: str) -> Socket:
        """A plain colour everywhere."""
        ...

    def output(self, colour: Socket) -> None:
        """What the frame shows."""
        ...

"""What a vision model saw in a rendered picture or frame, for Jev to judge."""

from content.schemas.base import ImmutableModel


class Observation(ImmutableModel):
    """What a vision model reports seeing in one frame. Jev judges this text, not pixels."""

    subject: str
    setting: str
    composition: str
    # The medium it looks like: photograph, 3D render, painting, flat illustration...
    rendering_style: str
    dominant_colours: list[str]
    lighting: str
    visible_text: list[str]
    artefacts: list[str]
    # How enclosed or open the space is ("tight, walls close around the subject").
    framing: str = ""
    # Whether attention goes to one point or spreads across the frame.
    focus: str = ""


class Perception(ImmutableModel):
    observations: list[Observation]

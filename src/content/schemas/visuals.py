"""The storyboard: scenes, their anchors, and the public figures drawn in them."""

from typing import Literal

from pydantic import Field

from content.schemas.base import ImmutableModel
from content.schemas.references import ReferenceRequest
from content.schemas.story import Reaction

VisualFunction = Literal["show", "explain", "prove", "make_it_felt", "bridge"]


EvidencePresentation = Literal["reconstruction", "symbolic"]


class PublicFigure(ImmutableModel):
    """A public figure in frame, drawn as a stylised portrait or, failing that, a silhouette."""

    name: str
    # Features a reader would recognise in a drawn portrait.
    likeness: str
    # The same person as a shadowed silhouette, recognisable by outline alone.
    silhouette: str


class SceneAnchor(ImmutableModel):
    """The main scene: what must be in frame. Every image and video prompt is built from it."""

    subject: str
    setting: str
    composition: str
    key_elements: list[str]
    light_and_colour: str
    figure: PublicFigure | None = None


class Scene(ImmutableModel):
    scene_id: str
    script_unit_ids: list[str] = Field(min_length=1)
    purpose: str
    visual_function: VisualFunction
    evidence_presentation: EvidencePresentation
    anchor: SceneAnchor
    # Where the eye lands, in a few plain words a detector can find in the picture
    # ("the woman at the lectern"); the camera glides toward it and the frame
    # breathes around it. Never part of an image or video prompt.
    focus: str = ""
    # One of the theme's camera moves, by name.
    camera: str
    motion: str
    # What visibly carries this scene into the next one. Ignored for the final scene.
    morph_bridge: str
    # The storyboard's reference requests this scene is drawn from.
    reference_ids: list[str] = Field(default_factory=list)
    # A person's override of the scene's emotional field, from a `feel` note.
    feeling: Reaction | None = None


class VisualPackage(ImmutableModel):
    """The storyboard: ordered scenes that partition the narration."""

    overall_visual_direction: str
    scenes: list[Scene] = Field(min_length=1)
    continuity_notes: list[str]
    # Real people, places, and objects to find pictures of, so scenes show the story.
    references: list[ReferenceRequest] = Field(default_factory=list)

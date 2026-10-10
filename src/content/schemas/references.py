"""Reference photographs of the story's real people, places and objects."""

from typing import Literal

from content.schemas.base import ImmutableModel
from content.schemas.judgement import Judgement
from content.schemas.perception import Observation

ReferenceKind = Literal["person", "place", "object"]


class ReferenceRequest(ImmutableModel):
    """Something real the storyboard should be drawn from, requested by the Visual Director."""

    ref_id: str
    kind: ReferenceKind
    # What to search for: a name, a place, an object ("Ada Lovelace", "punch card").
    query: str
    unit_ids: list[str]
    purpose: str


class FoundImage(ImmutableModel):
    """A search result, with the rights information the source provides."""

    source: str
    title: str
    description: str
    image_url: str
    page_url: str
    licence: str | None
    author: str | None
    width: int
    height: int


class ReferenceImage(ImmutableModel):
    found: FoundImage
    path: str
    observation: Observation
    judgement: Judgement


class ReferenceSet(ImmutableModel):
    """Everything found for one request, and the images keyframes will be drawn from."""

    request: ReferenceRequest
    # False when Jev judged the request irrelevant to its narration; nothing is searched.
    relevant: bool
    candidates: list[ReferenceImage]
    chosen: list[str]
    # Image URLs a person rejected; they are never offered again.
    rejected: list[str] = []

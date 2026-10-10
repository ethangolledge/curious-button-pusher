"""Pictures of the story's real people, places and objects: found, judged for relevance and
match, and kept with the run."""

from functools import partial
from pathlib import Path

from content.production.media import as_png
from content.production.studio import (
    Studio,
    required,
)
from content.providers.base import Usage
from content.providers.images import ImageSource
from content.schemas.judgement import Judgement
from content.schemas.references import FoundImage, ReferenceImage, ReferenceRequest, ReferenceSet
from content.state import CallRecord, ContentState
from content.story.notes import rejected_reference_ids


class References(Studio):
    def find_references(self, state: ContentState) -> ContentState:
        """Search, check, and choose images for every reference the storyboard asks for.

        A request found before is reused unchanged unless a person rejected its images."""
        visuals = required(state.get("visual_package"), "a storyboard")
        script = required(state.get("script_package"), "a script")
        texts = {unit.unit_id: unit.text for unit in script.script_units}
        existing = state.get("references", {})
        waiting = state.get("director_notes", [])
        # A person's R-note rejects that reference's picks; they are never offered again.
        rejections = rejected_reference_ids(waiting)
        references: dict[str, ReferenceSet] = {}
        judgements: list[Judgement] = []
        calls: list[CallRecord] = []
        for request in visuals.references:
            previous = existing.get(request.ref_id)
            if previous is not None and previous.request != request:
                previous = None
            rejecting = request.ref_id in rejections
            # Kept unless a person rejected it: what was chosen, or Jev's finding that the
            # request is irrelevant. A relevant request that found nothing is searched again.
            if (
                previous is not None
                and (previous.chosen or not previous.relevant)
                and not rejecting
            ):
                references[request.ref_id] = previous
                continue
            rejected = [] if previous is None else list(previous.rejected)
            if previous is not None and rejecting:
                rejected += [
                    candidate.found.image_url
                    for candidate in previous.candidates
                    if candidate.path in previous.chosen
                ]
            narration = " ".join(texts.get(unit_id, "") for unit_id in request.unit_ids)
            found, found_judgements, found_calls = self._find_reference(
                request, narration, rejected
            )
            references[request.ref_id] = found
            judgements += found_judgements
            calls += found_calls
        return {
            "references": references,
            "director_notes": [note for note in waiting if not note.startswith("R")],
            "judgements": judgements,
            "call_log": calls,
        }

    def _find_reference(
        self, request: ReferenceRequest, narration: str, rejected: list[str]
    ) -> tuple[ReferenceSet, list[Judgement], list[CallRecord]]:
        relevance, relevance_call = self.judge.evaluate(
            {
                "stage": "references",
                "revision": 0,
                "target": "reference",
                "target_id": request.ref_id,
                "state": {
                    "query": request.query,
                    "kind": request.kind,
                    "purpose": request.purpose,
                    "narration": narration,
                },
                "expected": None,
            }
        )
        calls = [relevance_call]
        if any(judgement.outcome == "fail" for judgement in relevance):
            return (
                ReferenceSet(request=request, relevant=False, candidates=[], chosen=[]),
                relevance,
                calls,
            )
        found, paths, download_calls = self._download_candidates(request, rejected)
        calls += download_calls
        if not paths:
            empty = ReferenceSet(
                request=request, relevant=True, candidates=[], chosen=[], rejected=rejected
            )
            return empty, relevance, calls
        observations, perception_calls = self.perceive(paths)
        calls += perception_calls
        candidates = []
        judgements = list(relevance)
        for index, (image, path, observation) in enumerate(
            zip(found, paths, observations, strict=True), start=1
        ):
            (match,), match_call = self.judge.evaluate(
                {
                    "stage": "references",
                    "revision": 0,
                    "target": "reference_image",
                    "target_id": f"{request.ref_id}#{index}",
                    "state": {
                        "query": request.query,
                        "kind": request.kind,
                        "title": image.title,
                        "description": image.description,
                        "observation": observation.model_dump(),
                    },
                    "expected": None,
                }
            )
            calls.append(match_call)
            judgements.append(match)
            candidates.append(
                ReferenceImage(
                    found=image, path=str(path), observation=observation, judgement=match
                )
            )
        ranked = sorted(
            (candidate for candidate in candidates if candidate.judgement.outcome == "pass"),
            key=lambda candidate: -(candidate.judgement.answer.noul or 0),
        )
        chosen = [candidate.path for candidate in ranked[: self.config.references_per_request]]
        return (
            ReferenceSet(
                request=request,
                relevant=True,
                candidates=candidates,
                chosen=chosen,
                rejected=rejected,
            ),
            judgements,
            calls,
        )

    def _download_candidates(
        self, request: ReferenceRequest, rejected: list[str]
    ) -> tuple[list[FoundImage], list[Path], list[CallRecord]]:
        """The first sources' results that are large enough and not rejected, downloaded
        into the cache as PNGs."""
        found: list[FoundImage] = []
        paths: list[Path] = []
        calls: list[CallRecord] = []
        wanted = self.config.reference_candidates
        for source in self.image_sources:
            for image in source.search(request.query, limit=wanted * 2):
                if len(found) == wanted:
                    break
                too_small = min(image.width, image.height) < self.config.min_reference_side
                if too_small or image.image_url in rejected:
                    continue
                path, download_calls = self.fetch(
                    "reference",
                    {"url": image.image_url},
                    ".png",
                    "reference_download",
                    partial(_download, source, image.image_url),
                    about=f"reference photo: {image.image_url}",
                )
                found.append(image)
                paths.append(path)
                calls += download_calls
            if found:
                break
        return found, paths, calls


def _download(source: ImageSource, url: str) -> tuple[bytes, Usage]:
    return as_png(source.download(url)), Usage(model=source.name, cost_usd=0.0)

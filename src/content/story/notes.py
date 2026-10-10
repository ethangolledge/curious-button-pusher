"""A person's notes, read: each sent to whoever owns what it is about.

Notes start with the ID of what they target: `U3:` a narration unit (the writer), `S4:` a
scene (the Visual Director), `R2:` a reference image (its picks are rejected and searched
again), `P2 [class]:` a narration passage, by what is wrong with it (see `NarrationFixes`).
Notes without an ID are sorted into targeted ones by the critic."""

import re
from dataclasses import dataclass, field
from typing import cast

from content.schemas.story import Reaction

TARGET = re.compile(r"\b([USRP]\d+)(?:\s*\[([a-z ]+)\])?\s*[:\-–]\s*")


# "Eniac = EN-ee-ack": a word, and how the voice should say it.
SAY_AS = re.compile(r"^\s*(.+?)\s*=\s*(.+?)\s*\.?$")


# "S4: feel brace" sets that scene's emotional field directly, without a redesign.
FEEL = re.compile(r"^(S\d+): feel (lean_in|brace|recoil|settle)\.?$")


@dataclass
class DirectorNotes:
    units: list[str] = field(default_factory=list)
    scenes: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    passages: list[str] = field(default_factory=list)
    untargeted: str = ""

    def add(self, note: str) -> None:
        kind = note[0]
        {"U": self.units, "S": self.scenes, "R": self.references, "P": self.passages}[kind].append(
            note
        )


def split_notes(text: str) -> DirectorNotes:
    """Each targeted note runs from its ID to the next ID; anything before the first ID
    is untargeted."""
    notes = DirectorNotes()
    matches = list(TARGET.finditer(text))
    notes.untargeted = (text[: matches[0].start()] if matches else text).strip()
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip().rstrip(";").strip()
        if body:
            kind = f" [{match.group(2).strip()}]" if match.group(2) else ""
            notes.add(f"{match.group(1)}{kind}: {body}")
    return notes


@dataclass
class NarrationFixes:
    """A person's notes on narration passages, each turned into the smallest fix that
    re-records only its passage."""

    # wording: notes on the passage's lines, for a line edit.
    unit_notes: list[str] = field(default_factory=list)
    # pronunciation: how the voice should say a word, added to the script's `say_as`.
    say_as: dict[str, str] = field(default_factory=dict)
    # pause or emphasis: added to that passage's direction.
    directions: dict[str, str] = field(default_factory=dict)
    # voice: a fresh take of the passage.
    retakes: set[str] = field(default_factory=set)


def narration_fixes(notes: list[str], passage_units: dict[str, list[str]]) -> NarrationFixes:
    """Route each `P2 [class]: …` note by its class. A note with no class is about the
    wording; a pronunciation note that does not read "word = how to say it" becomes a
    direction for the passage instead."""
    fixes = NarrationFixes()
    for note in notes:
        head, body = note.split(":", 1)
        passage_id = head.split()[0]
        kind = head[len(passage_id) :].strip(" []") or "wording"
        body = body.strip()
        units = passage_units.get(passage_id)
        if units is None:
            continue
        if kind == "pronunciation" and (say := SAY_AS.match(body)):
            fixes.say_as[say.group(1)] = say.group(2)
        elif kind in {"pronunciation", "pause"}:
            fixes.directions[passage_id] = body
        elif kind == "voice":
            fixes.retakes.add(passage_id)
        else:
            fixes.unit_notes.append(f"{', '.join(units)}: {body}")
    return fixes


# What can be wrong with a narration passage, each fixed its own way (`narration_fixes`).
PASSAGE_CLASSES = ("wording", "pronunciation", "pause", "voice")


def rejected_reference_ids(notes: list[str]) -> set[str]:
    return {note.split(":", 1)[0] for note in notes if note.startswith("R")}


def feel_overrides(notes: list[str]) -> tuple[dict[str, Reaction], list[str]]:
    """Split `feel` notes (scene ID to reaction) from the scene notes that need a redesign."""
    overrides: dict[str, Reaction] = {}
    rest = []
    for note in notes:
        if match := FEEL.match(note.strip()):
            overrides[match.group(1)] = cast(Reaction, match.group(2))
        else:
            rest.append(note)
    return overrides, rest

"""Where a channel's models come from and how they are drawn: only freely usable models are
offered, best match first; an imported model's surfaces take the roles their colours are
nearest; a version of a model is the same shape repainted and resized, made from the
original's file (or code) and carrying its rights."""

from pathlib import Path

import pytest

from content.blender.job import ActorCall, BlockCall, Job
from content.blender.materials import linear, nearest_role
from content.providers.assets import Candidate, licence_terms
from content.staging.catalogue import load_catalogue, with_models
from content.staging.library import Model
from content.staging.sourcing import TOO_DETAILED, rank


@pytest.mark.parametrize(
    ("label", "terms"),
    [
        ("CC0 Public Domain", "CC0"),
        ("Creative Commons Zero v1.0 Universal", "CC0"),
        ("CC Attribution", "CC-BY"),
        ("CC-BY 3.0", "CC-BY"),
        ("Creative Commons Attribution 4.0 International", "CC-BY"),
        ("CC Attribution-ShareAlike", ""),
        ("CC Attribution-NonCommercial", ""),
        ("CC Attribution-NoDerivs", ""),
        ("CC-BY-NC-SA 4.0", ""),
        ("Standard", ""),
    ],
)
def test_only_licences_that_allow_any_use_with_at_most_a_credit_are_accepted(
    label: str, terms: str
) -> None:
    assert licence_terms(label) == terms


def _candidate(title: str, licence: str = "CC0", faces: int = 1000, page: str = "") -> Candidate:
    return Candidate("a source", title, page or f"https://models/{title}", "", "glb", licence,
                     "a maker", faces)  # fmt: skip


def test_a_search_offers_usable_models_once_each_best_match_first() -> None:
    found = [
        _candidate("Office chair with wheels"),
        _candidate("Oil tanker"),
        _candidate("Oil tanker (share alike)", licence=""),
        _candidate("Oil tanker, every rivet", faces=TOO_DETAILED + 1),
        _candidate("Tanker ship", licence="CC-BY"),
        _candidate("Oil tanker", page="https://models/Oil tanker"),
    ]

    shortlist = rank("oil tanker", found)

    assert [c.title for c in shortlist] == ["Oil tanker", "Tanker ship", "Office chair with wheels"]


@pytest.mark.parametrize(
    ("colour", "metallic", "transmission", "role"),
    [
        ("#f4f4f2", 0.0, 0.0, "paper"),  # a white mug
        ("#8e2a24", 0.0, 0.0, "brick"),  # a deep red
        ("#3a2a1a", 0.0, 0.0, "dark_wood"),
        ("#2e5e2e", 0.0, 0.0, "foliage"),
        ("#202020", 0.0, 0.0, "rubber"),
        ("#c0c0c0", 1.0, 0.0, "metal"),  # what makes metal is its finish, not its colour
        ("#ffffff", 0.0, 0.95, "glass"),
    ],
)
def test_an_imported_surface_takes_the_role_it_is_most_like(
    colour: str, metallic: float, transmission: float, role: str
) -> None:
    assert nearest_role(linear(colour), metallic=metallic, transmission=transmission) == role


def test_a_version_is_its_original_repainted_and_resized_with_its_rights(
    tmp_path: Path,
) -> None:
    theme = tmp_path / "channel"
    catalogue = load_catalogue(theme)
    library = catalogue.library
    library.add(
        Model(
            model_id="statue", names=("bust",), describe="A marble bust", size=(0.4, 0.3, 0.6),
            source="sketchfab", licence="CC-BY", page="https://statue", author="a sculptor",
            file="statue.glb",
        )
    )  # fmt: skip
    library.vary("gold_statue", "statue", describe="The bust in gold", paint={"stone": "metal"})
    library.vary(
        "tall_gold_statue", "gold_statue", describe="Taller", paint={"base": "wood"}, height=1.2
    )
    library.vary("red_box", "cardboard_box", describe="A red box", paint={"card": "brick"})
    with pytest.raises(ValueError, match="no role velvet"):
        library.vary("velvet_box", "cardboard_box", describe="?", paint={"card": "velvet"})

    job = Job(
        shot_id="s", seconds=1, layout=BlockCall("studio"), camera=BlockCall("hold"),
        look=BlockCall("plain"),
        actors=tuple(
            ActorCall(m, "prop", m) for m in ("tall_gold_statue", "red_box", "cardboard_box")
        ),
    )  # fmt: skip
    shipped = {m.model_id: m for m in with_models(job, catalogue).models}

    tall = shipped["tall_gold_statue"]
    assert tall.path.endswith("statue.glb") and not tall.prop
    assert tall.paint == {"stone": "metal", "base": "wood"}
    assert tall.height == 1.2 and tall.size == (0.8, 0.6, 1.2)
    box = shipped["red_box"]
    assert box.prop == "cardboard_box" and not box.path and box.paint == {"card": "brick"}
    assert "cardboard_box" not in shipped  # made in code: Blender builds it from its file
    # Whoever made the original is credited for every version of it.
    assert library.credit("tall_gold_statue") == (
        "A marble bust by a sculptor (sketchfab, CC-BY): https://statue"
    )
    assert library.credit("red_box") == ""

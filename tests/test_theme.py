import json
import re
import shutil
from pathlib import Path

import pytest

from content.config import write_channel_config
from content.schemas.script import VoiceDirection
from content.schemas.visuals import PublicFigure, SceneAnchor
from content.theme import (
    Theme,
    ThemeError,
    load_theme,
    narration_direction,
    new_theme,
    theme_guidance,
)

THEMES = Path(__file__).parents[1] / "themes"
THEME = THEMES / "starter"
EVERY_THEME = sorted(path for path in THEMES.iterdir() if (path / "theme.json").is_file())


@pytest.mark.parametrize("root", EVERY_THEME, ids=lambda path: path.name)
def test_every_theme_loads_with_its_assets(root: Path) -> None:
    theme = load_theme(root)

    assert theme.spec.name == root.name
    assert theme.font_file.is_file()
    assert theme.skill
    guidance = theme_guidance(theme)
    for name, move in theme.spec.visual.camera_moves.items():
        assert f"`{name}`: {move.describe}" in guidance


@pytest.mark.parametrize("root", EVERY_THEME, ids=lambda path: path.name)
def test_every_theme_describes_a_style_never_a_subject(root: Path) -> None:
    visual = load_theme(root).spec.visual
    style_text = " ".join(
        [visual.style, visual.texture, visual.lighting, visual.morph, visual.tone.darker]
        + [move.describe for move in visual.camera_moves.values()]
    ).lower()

    subjects = ["city", "gotham", "skyline", "tower", "street", "rain", "art deco", "batman"]
    assert [word for word in subjects if re.search(rf"\b{word}\b", style_text)] == []


def test_prompts_are_built_from_scene_slots() -> None:
    theme = load_theme(THEME)
    anchor = SceneAnchor(
        subject="a brass cipher machine",
        setting="a dark oak desk",
        composition="close, centred",
        key_elements=["rotors", "teal glow"],
        light_and_colour="teal rim light",
    )
    following = anchor.model_copy(
        update={"subject": "a spiral of snow", "setting": "the Alps at night"}
    )

    keyframe = theme.keyframe_prompt(anchor)
    segment = theme.segment_prompt(
        anchor,
        camera="push_in",
        motion="the rotors turn",
        morph_bridge="the rotor spiral",
        next_anchor=following,
    )

    assert "Main scene: a brass cipher machine, in a dark oak desk" in keyframe
    assert "Key elements: rotors, teal glow" in keyframe
    assert "held for a beat with a slow push-in" in segment
    assert "the rotor spiral becomes the next scene" in segment
    assert "It lands exactly on a spiral of snow" in segment
    # Stills and morphs each carry their own avoid list from the theme.
    assert theme.spec.visual.avoid in keyframe
    assert theme.spec.visual.morph_avoid in segment
    final = theme.segment_prompt(
        anchor, camera="drift", motion="still", morph_bridge="none", next_anchor=None
    )
    assert "becomes the next scene" not in final


def test_lexicon_writes_narration_as_it_is_spoken() -> None:
    theme = load_theme(THEME)
    voice = theme.spec.voice.model_copy(
        update={"lexicon": {"MBW": "M-B-W", "BBC": "B-B-C", "AG": "A-G"}}
    )
    theme = Theme(theme.root, theme.spec.model_copy(update={"voice": voice}), theme.skill)

    assert theme.spoken_text("The MBW and the BBC met at Thames AG.") == (
        "The M-B-W and the B-B-C met at Thames A-G."
    )
    assert theme.spoken_text("AGENTS") == "AGENTS"


def test_template_typos_and_missing_files_fail_at_load(tmp_path: Path) -> None:
    root = tmp_path / "theme"
    shutil.copytree(THEME, root)
    spec = json.loads((root / "theme.json").read_text(encoding="utf-8"))
    spec["visual"]["keyframe_template"] = "{style} {subjekt}"
    (root / "theme.json").write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ThemeError, match="unknown slots: subjekt"):
        load_theme(root)

    shutil.copytree(THEME, tmp_path / "second")
    (tmp_path / "second/fonts/ArchivoBlack-Regular.ttf").unlink()
    with pytest.raises(ThemeError, match="Theme files are missing"):
        load_theme(tmp_path / "second")


def test_a_public_figure_is_drawn_by_the_theme_then_as_a_silhouette() -> None:
    theme = load_theme(THEME)
    anchor = SceneAnchor(
        subject="a man at a lectern",
        setting="a lecture hall",
        composition="close",
        key_elements=["lectern"],
        light_and_colour="dim lamp light",
        figure=PublicFigure(
            name="Ada Lovelace",
            likeness="lean face, dark side-parted hair, slim navy suit",
            silhouette="a slim figure in a narrow suit with side-parted hair",
        ),
    )

    portrait = theme.keyframe_prompt(anchor)
    silhouette = theme.keyframe_prompt(anchor, silhouette=True)

    assert "the figure is Ada Lovelace" in portrait
    assert "lean face, dark side-parted hair" in portrait
    assert "Ada Lovelace" not in silhouette
    assert "a slim figure in a narrow suit" in silhouette


def test_a_new_theme_starts_as_a_copy_of_the_starter(tmp_path: Path) -> None:
    created = new_theme(THEME, tmp_path / "my-channel")

    assert load_theme(created).spec.name == "my-channel"
    with pytest.raises(ThemeError, match="already exists"):
        new_theme(THEME, tmp_path / "my-channel")


def test_a_new_channel_gets_its_own_configuration_beside_its_theme(tmp_path: Path) -> None:
    theme = new_theme(THEME, tmp_path / "my-channel")
    written = write_channel_config(THEMES.parent / "config/config.example.json", theme, "a-bucket")

    data = json.loads(written.read_text(encoding="utf-8"))
    assert written == theme / "config.json"
    assert data["theme"] == theme.as_posix()
    assert data["learning"]["directory"] == (theme / "learning").as_posix()
    assert data["storage"] == {"bucket": "a-bucket"}


def test_each_passage_is_directed_by_its_beat_from_the_script() -> None:
    theme = load_theme(THEME)
    voice = theme.spec.voice.model_copy(update={"direction_style": "inline"})
    theme = Theme(theme.root, theme.spec.model_copy(update={"voice": voice}), theme.skill)
    script = VoiceDirection(
        tone="Wry and conversational",
        pace="",
        delivery="plain storytelling",
        beats={"P3": "slower; let the figure land"},
    )

    assert narration_direction(theme, script, "P3") == (
        "Wry and conversational; slower; let the figure land"
    )
    assert narration_direction(theme, script, "P1") == "Wry and conversational; plain storytelling"
    # Only a script that gives no direction falls back to the theme's.
    assert narration_direction(theme, None, "P1") == voice.direction
    silent = Theme(
        theme.root,
        theme.spec.model_copy(
            update={"voice": voice.model_copy(update={"direction_style": "none"})}
        ),
        theme.skill,
    )
    assert narration_direction(silent, script, "P3") is None

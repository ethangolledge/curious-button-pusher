"""One channel, several shapes of video: each video picks its format, length, scenes and
cap; the look, voice and music stay the channel's."""

from pathlib import Path

import pytest

from content.choices import RunChoices, configure_run
from content.config import ContentConfig, load_config
from content.production.budget import (
    Pricing,
    estimate_video,
    recommended_scenes,
    scene_options,
)
from content.schemas.review import ReviewRequest
from content.schemas.visuals import SceneAnchor
from content.theme import ThemeError, load_theme
from content.workflow.estimate import estimate_table
from content.workflow.review_requests import start_request

ROOT = Path(__file__).parents[1]
PRICES = Pricing(cap=4.5, image_usd=0.045, video_usd_per_second=0.03, morph_seconds=4)


def test_a_long_video_is_widescreen_with_its_own_subtitles_and_a_plan_sign_off(
    app_config: ContentConfig,
) -> None:
    config = configure_run(app_config, RunChoices(format="long", seconds=480))
    shape = config.theme.spec.format

    assert (shape.width, shape.height, shape.aspect_ratio) == (1920, 1080, "16:9")
    assert config.theme.spec.subtitles.max_words == shape.subtitle_max_words
    assert config.workflow.review_plan
    # A chosen length may run 30% over, no more.
    assert shape.max_seconds == 624
    # The channel's look is unchanged.
    assert config.theme.spec.visual == app_config.theme.spec.visual


def test_the_short_format_keeps_its_prompts_word_for_word() -> None:
    # Cached pictures are keyed by their prompt: naming the frame must not redraw them.
    theme = load_theme(ROOT / "themes/starter")
    anchor = SceneAnchor.model_validate(
        {
            "subject": "a ledger",
            "setting": "an office",
            "composition": "close",
            "key_elements": ["ink"],
            "light_and_colour": "low lamp",
        }
    )

    assert theme.keyframe_prompt(anchor).startswith("Vertical 9:16 illustration")
    assert theme.with_format("long").keyframe_prompt(anchor).startswith("Widescreen 16:9")
    with pytest.raises(ThemeError):
        theme.with_format("square")


def test_choices_given_later_replace_only_what_they_set() -> None:
    saved = RunChoices(format="long", seconds=480, scenes=24)

    assert saved.merged(RunChoices(max_usd=15)) == RunChoices(
        format="long", seconds=480, scenes=24, max_usd=15
    )


def test_a_chosen_cap_replaces_the_configured_one() -> None:
    config = load_config(ROOT / "config/config.fake-video.json")

    capped = configure_run(config, RunChoices(max_usd=12.5))

    assert capped.production is not None and capped.production.max_usd == 12.5


def test_scene_options_and_their_cost() -> None:
    assert recommended_scenes(75) == 6  # a picture about every 12 s in a short
    assert recommended_scenes(480) == 24  # every 20 s in long form
    assert scene_options(480) == [96, 60, 40, 24, 16]

    estimate = estimate_video(480, 24, PRICES, expected_takes=1.3)

    assert estimate.hold_seconds == 20
    assert estimate.pictures == pytest.approx(24 * PRICES.keyframe)
    assert estimate.morphs == pytest.approx(23 * PRICES.morph)
    # Writing is scaled up from short runs for a long story.
    assert estimate.writing[0] > 1.5 * 2.5


def test_the_start_sign_off_shows_the_videos_shape_and_cost() -> None:
    config = configure_run(
        load_config(ROOT / "config/config.fake-video.json"),
        RunChoices(format="long", seconds=480, scenes=30),
    )

    snapshot = start_request("A topic", None, config, RunChoices(seconds=480, scenes=30)).snapshot

    assert "16:9" in snapshot and "Scenes: 30." in snapshot
    assert "story plan" in snapshot
    assert "| 30 |" in estimate_table(config, 480, 30)
    assert ReviewRequest(stage="plan", reason="").sign_off

import re
import shutil
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import BaseModel

from content.blender.job import Job, Join
from content.choices import RunChoices, configure_run
from content.config import ContentConfig, load_config
from content.production import ffmpeg
from content.production.checks import hard_cuts, integrated_loudness
from content.production.media import FakeMediaProvider, GenerationRefused
from content.production.music_map import MusicMap, MusicSection, save_map
from content.production.producer import Producer
from content.production.score import arrangements
from content.production.studio import NarrationTask
from content.providers.base import Usage
from content.providers.blender import FakeBlender
from content.providers.fake import FakeDecisionProvider, FakeModelProvider
from content.providers.images import FakeImageSource
from content.schemas.plan import EditorialBrief
from content.schemas.review import ReviewRequest, ReviewResponse
from content.schemas.visuals import VisualPackage
from content.staging.backlog import most_wanted
from content.state import ContentOutput
from content.theme import Theme
from content.workflow.checkpoint import create_checkpointer
from content.workflow.demo import demo_answer, demo_response
from content.workflow.graph import build_graph
from content.workflow.run import create_initial_state

pytestmark = pytest.mark.skipif(not ffmpeg.available(), reason="ffmpeg is not installed")


@pytest.fixture
def video_config(project_root: Path, tmp_path: Path) -> ContentConfig:
    """The fake-video config, with a private cache and a small, slow frame so encoding is
    quick: what these tests check (joins, timing, caching, retries) does not depend on it."""
    config = load_config(project_root / "config/config.fake-video.json")
    assert config.production is not None
    small = config.theme.spec.format.model_copy(update={"width": 270, "height": 480, "fps": 10})
    theme = Theme(
        config.theme.root,
        config.theme.spec.model_copy(update={"format": small}),
        config.theme.skill,
    )
    return replace(
        config,
        theme=theme,
        production=replace(config.production, cache_directory=tmp_path),
    )


@pytest.mark.video
def test_a_staged_channel_renders_the_scenes_it_can_stage_and_draws_the_rest(
    video_config: ContentConfig, tmp_path: Path
) -> None:
    assert video_config.production is not None
    # A copy of the channel: what it could not stage is noted in its folder.
    root = tmp_path / "channel"
    shutil.copytree(video_config.theme.root, root)
    theme = Theme(root, video_config.theme.spec, video_config.theme.skill)
    config = replace(
        video_config,
        theme=theme,
        production=replace(video_config.production, pictures="staged"),
    )
    media, blender = FakeMediaProvider(), FakeBlender()

    result, reviews = _run(config, media, renderer=blender)

    package = result["final_package"]
    assert package is not None and package.production is not None
    keyframes = result["keyframes"]
    staged = sorted(scene for scene, asset in keyframes.items() if asset.shot)
    assert staged == ["S2", "S4"]
    # Their pictures cost nothing: only the four drawn scenes asked the image model.
    assert media.calls.count("image") == 4
    # Stills to judge, then a draft for the animatic, then the final shot for the cut.
    qualities = [(job.shot_id, job.quality) for job in blender.jobs if isinstance(job, Job)]
    assert qualities.count(("S2", "final")) == 2 and ("S2", "draft") in qualities
    # The morphs into and out of a staged scene start and end on its shot's own frames.
    morph_into = next(t for t in result["segments"].values() if t.scene_id == "S1")
    assert morph_into.rendered
    assert keyframes["S2"].first_frame.endswith("0001.png")
    info = ffmpeg.probe(Path(package.production.video_path))
    assert info.duration == pytest.approx(package.production.scenes[-1].end, abs=0.2)
    assert [review.stage for review in reviews] == ["storyboard", "final_cut"]
    assert most_wanted(root) == [("layout: a reading room", 1)]


@pytest.mark.video
def test_rendered_joins_replace_every_paid_morph(video_config: ContentConfig) -> None:
    assert video_config.production is not None
    config = replace(video_config, production=replace(video_config.production, joins="rendered"))
    media, blender = FakeMediaProvider(), FakeBlender()

    result, _ = _run(config, media, renderer=blender)

    package = result["final_package"]
    assert package is not None and package.production is not None
    assert "video" not in media.calls
    joins = [job for job in blender.jobs if isinstance(job, Join)]
    timeline = result["timeline"]
    assert timeline is not None and len(joins) == len(timeline.transitions) > 0
    # Each join's transition is the theme's for how the feeling shifts.
    presets = {preset.block for preset in config.theme.spec.staging.joins.values()}
    assert {join.transition.block for join in joins} <= presets
    assert all(asset.rendered for asset in result["segments"].values())


@pytest.mark.video
def test_approved_run_produces_a_platform_ready_video(video_config: ContentConfig) -> None:
    media = FakeMediaProvider()
    result, reviews = _run(video_config, media)

    package = result["final_package"]
    assert package is not None and package.production is not None
    production = package.production
    video = Path(production.video_path)
    info = ffmpeg.probe(video)
    assert (info.width, info.height, info.fps) == (270, 480, 10)
    assert info.duration == pytest.approx(production.scenes[-1].end, abs=0.2)
    assert integrated_loudness(video) == pytest.approx(-14, abs=1.0)
    assert Path(production.contact_sheet_path).is_file()
    assert [review.stage for review in reviews] == ["storyboard", "final_cut"]
    assert production.contact_sheet_path in reviews[0].attachments
    sheet = Path(reviews[0].attachments[0])
    page = sheet.read_text(encoding="utf-8")
    assert sheet.name == "index.html"
    assert "One source says it happened" in page
    assert "national archives reading room (1)" in page and "CC BY 4.0" in page
    assert "class='arc'" in page and "lean in · strong" in page
    assert all((sheet.parent / src).is_file() for src in re.findall(r"src='([^']+)'", page))
    animatic = Path(reviews[0].attachments[1])
    assert animatic.name.endswith(".mp4") and "animatic" in str(animatic)
    assert ffmpeg.probe(animatic).duration == pytest.approx(production.scenes[-1].end, abs=0.3)
    assert [scene.scene_id for scene in production.scenes] == ["S1", "S2", "S3", "S4", "S5", "S6"]
    stages = {judgement.stage for judgement in result["judgements"]}
    assert {"keyframes", "segments"} <= stages
    assert media.calls.count("image") == 6
    # Every scene is a motion still, and AI video morphs across every join between them,
    # within the budget; the story sheet says what it costs.
    timeline, budget = result["timeline"], result["budget"]
    assert timeline is not None and budget is not None
    transitions = timeline.transitions
    assert len(transitions) == len(production.scenes) - 1
    assert media.calls.count("video") == len(transitions)
    assert set(result["segments"]) == {t.from_scene_id for t in transitions}
    assert budget.projected <= budget.cap
    assert "Projected cost $" in page


@pytest.mark.video
def test_an_irrelevant_reference_is_dropped_before_any_search(
    video_config: ContentConfig,
) -> None:
    def irrelevant(question_id: str, state: Mapping[str, Any]) -> Any:
        if question_id == "reference_relevant":
            return {"kind": "noul", "noul": 0.05}
        return demo_answer(question_id, state)

    source = FakeImageSource()
    graph_media = FakeMediaProvider()

    result, _ = _run(
        video_config, graph_media, decisions=FakeDecisionProvider(irrelevant), source=source
    )

    assert source.searches == []
    assert result["references"]["R1"].relevant is False
    assert not result["keyframes"]["S2"].prompt.endswith(
        video_config.theme.spec.visual.reference_note
    )


@pytest.mark.video
def test_rejecting_a_reference_redraws_only_the_scenes_drawn_from_it(
    video_config: ContentConfig,
) -> None:
    media = FakeMediaProvider()
    answers = iter(
        [
            ReviewResponse(action="revise", feedback="R1: that is the wrong building"),
            ReviewResponse(action="approve"),
            ReviewResponse(action="approve"),
        ]
    )

    result, reviews = _run(video_config, media, respond=lambda _: next(answers))

    assert [review.stage for review in reviews] == ["storyboard", "storyboard", "final_cut"]
    reference = result["references"]["R1"]
    assert len(reference.rejected) == 2
    assert not set(reference.chosen) & {
        candidate.path
        for candidate in reference.candidates
        if candidate.found.image_url in reference.rejected
    }
    # Only S2 is drawn from R1, so only its keyframe is drawn again.
    assert media.calls.count("image") == 7


@pytest.mark.video
def test_a_feel_note_reshapes_one_scene_without_a_redesign(video_config: ContentConfig) -> None:
    provider = FakeModelProvider(default_factory=demo_response)
    media = FakeMediaProvider()
    answers = iter(
        [
            ReviewResponse(action="revise", feedback="S4: feel brace"),
            ReviewResponse(action="approve"),
            ReviewResponse(action="approve"),
        ]
    )

    result, reviews = _run(video_config, media, provider=provider, respond=lambda _: next(answers))

    assert [review.stage for review in reviews] == ["storyboard", "storyboard", "final_cut"]
    assert sum(call.output_type is VisualPackage for call in provider.calls) == 1
    brace = video_config.theme.spec.visual.field.reactions["brace"]
    assert any(frame in result["keyframes"]["S4"].prompt for frame in brace.frame)
    assert media.calls.count("image") == 7


LIKENESS = "lean face, side-parted hair"


class RefusesPortraits(FakeMediaProvider):
    """Stands in for an image model whose policy declines drawn likenesses: any prompt
    describing the figure's face. A silhouette describes only its outline."""

    def image(self, **request: Any) -> Any:
        if LIKENESS in request["prompt"]:
            self.calls.append("refused")
            raise GenerationRefused("likeness declined")
        return super().image(**request)


@pytest.mark.video
def test_a_refused_portrait_is_redrawn_as_a_silhouette(video_config: ContentConfig) -> None:
    storyboard = demo_response('{"topic": "x"}', VisualPackage)
    assert isinstance(storyboard, dict)
    storyboard["scenes"][0]["anchor"]["figure"] = {
        "name": "A Public Figure",
        "likeness": LIKENESS,
        "silhouette": "a slim figure in a narrow suit",
    }
    provider = FakeModelProvider({VisualPackage: [storyboard]}, default_factory=demo_response)
    media = RefusesPortraits()

    result, reviews = _run(video_config, media, provider=provider)

    assert media.calls.count("refused") == 1
    keyframe = result["keyframes"]["S1"]
    assert keyframe.silhouette and keyframe.rendered
    assert "a slim figure in a narrow suit" in keyframe.prompt
    assert LIKENESS not in keyframe.prompt
    assert "A Public Figure" not in result["segments"]["S1"].prompt
    assert result["status"] == "approved"


@pytest.mark.video
def test_a_locked_music_track_replaces_generated_music(
    video_config: ContentConfig, tmp_path: Path
) -> None:
    track = tmp_path / "bed.wav"
    ffmpeg.run("-f", "lavfi", "-i", "anoisesrc=color=brown:duration=12:amplitude=0.1", track)
    spec = video_config.theme.spec
    music = spec.music.model_copy(update={"track": str(track)})
    theme = Theme(
        video_config.theme.root,
        spec.model_copy(update={"music": music}),
        video_config.theme.skill,
    )
    media = FakeMediaProvider()

    result, _ = _run(replace(video_config, theme=theme), media)

    assert "music" not in media.calls
    package = result["final_package"]
    assert package is not None and package.production is not None
    assert "music-bed" in str(package.production.music_path)


@pytest.mark.video
def test_a_mapped_bed_is_scored_to_the_story_on_one_beat(
    video_config: ContentConfig, tmp_path: Path
) -> None:
    track = tmp_path / "bed.wav"
    ffmpeg.run("-f", "lavfi", "-i", "anoisesrc=color=brown:duration=50:amplitude=0.1", track)
    # 120 BPM in two-second bars; as written, it holds the demo story's 45 s narration.
    music = MusicMap(
        beats=[0.5 * index for index in range(100)],
        downbeats=[2.0 * index for index in range(25)],
        duration=50.0,
        sections=[
            MusicSection(label="intro", start_bar=0, end_bar=4, energy=0.2),
            MusicSection(label="build", start_bar=4, end_bar=10, energy=0.6),
            MusicSection(label="peak", start_bar=10, end_bar=18, energy=1.0),
            MusicSection(label="outro", start_bar=18, end_bar=25, energy=0.4),
        ],
    )
    save_map(music, track.with_suffix(".map.json"))
    spec = video_config.theme.spec
    theme = Theme(
        video_config.theme.root,
        spec.model_copy(update={"music": spec.music.model_copy(update={"track": str(track)})}),
        video_config.theme.skill,
    )

    # A longer clip length leaves room to move lines onto the beat; without room, the
    # narration keeps its own timing and every scene still fits.
    assert video_config.production is not None
    production = replace(video_config.production, video_durations=(4, 6, 8, 10))
    config = replace(video_config, theme=theme, production=production)

    result, _ = _run(config, FakeMediaProvider())

    timeline = result["timeline"]
    assert timeline is not None
    assert [span.label for span in timeline.score][:3] == ["intro", "build", "peak"]
    # The edit is chosen after the narration is spoken: the video runs to its end, the
    # last picture holding while the track plays out for at least the shortest outro.
    edits = arrangements(music, spec.format.max_seconds)
    assert timeline.total_seconds in {edit.seconds for edit in edits}
    outro = config.theme.spec.music.outro_seconds
    assert timeline.scenes[-1].end + outro[0] <= timeline.total_seconds + 0.01
    package = result["final_package"]
    assert package is not None and package.production is not None
    assert "/score/" in str(package.production.music_path)
    video = ffmpeg.probe(Path(package.production.video_path))
    assert video.duration == pytest.approx(timeline.total_seconds, abs=0.2)


def test_a_take_too_slow_to_fix_is_recorded_again(
    video_config: ContentConfig, tmp_path: Path
) -> None:
    class SlowFirstTake(FakeMediaProvider):
        """The first take comes back at half pace."""

        def speech(self, **request: Any) -> tuple[bytes, Usage]:
            self.SECONDS_PER_SYLLABLE = FakeMediaProvider.SECONDS_PER_SYLLABLE * (
                2 if "speech" not in self.calls else 1
            )
            return super().speech(**request)

    production_config = video_config.production
    assert production_config is not None
    theme = video_config.theme
    voice = theme.spec.voice.model_copy(update={"tempo_range": (0.9, 1.2), "retakes": 2})
    theme = Theme(theme.root, theme.spec.model_copy(update={"voice": voice}), theme.skill)

    def producer(media: FakeMediaProvider, cache: str) -> Producer:
        production = replace(production_config, cache_directory=tmp_path / cache)
        return Producer(
            config=production,
            theme=theme,
            media=media,
            judge=cast(Any, None),
            image_sources=[],
        )

    text = "The river carried the sewage past Parliament, and for weeks nobody could breathe."
    steady = FakeMediaProvider()
    on_pace = producer(steady, "steady").narration._take(text, 0, None)[1]
    task = NarrationTask(
        passage_id="P1",
        unit_ids=["U1"],
        spoken_text=text,
        words_per_minute=on_pace,
        direction=None,
        first_take=0,
    )
    producer(steady, "steady").narration.narrate_passage(task)
    assert steady.calls.count("speech") == 1  # an on-pace take is never recorded again

    slow = SlowFirstTake()
    clip = producer(slow, "slow").narration.narrate_passage(task)["narration"]["P1"]

    assert slow.calls.count("speech") == 2
    assert clip.tempo == 1.0
    assert not any("limit" in issue for issue in clip.issues)

    class SomewhatSlow(FakeMediaProvider):
        """Every take a little slower than the stretch can fully correct."""

        SECONDS_PER_SYLLABLE = FakeMediaProvider.SECONDS_PER_SYLLABLE * 1.3

    # Brought to within the length tolerance of the pace, it is kept: one take is the rule.
    somewhat = SomewhatSlow()
    kept = producer(somewhat, "somewhat").narration.narrate_passage(task)["narration"]["P1"]
    assert somewhat.calls.count("speech") == 1
    assert kept.tempo == 1.2


@pytest.mark.video
def test_a_long_form_video_is_widescreen_after_a_plan_sign_off(
    video_config: ContentConfig,
) -> None:
    config = configure_run(video_config, RunChoices(format="long", seconds=150))
    wide = config.theme.spec.format.model_copy(update={"width": 480, "height": 270})
    theme = Theme(
        config.theme.root, config.theme.spec.model_copy(update={"format": wide}), config.theme.skill
    )
    config = replace(config, theme=theme)

    result, reviews = _run(config, FakeMediaProvider(), duration_seconds=150)

    package = result["final_package"]
    assert package is not None and package.production is not None
    info = ffmpeg.probe(Path(package.production.video_path))
    assert (info.width, info.height) == (480, 270)
    assert reviews[0].stage == "plan" and reviews[0].sign_off


@pytest.mark.video
def test_rerun_reuses_every_paid_asset(video_config: ContentConfig) -> None:
    _run(video_config, FakeMediaProvider())
    media = FakeMediaProvider()

    _run(video_config, media)

    assert media.calls == []


@pytest.mark.video
def test_failed_keyframe_is_rerendered_before_the_storyboard(
    video_config: ContentConfig,
) -> None:
    spent: list[bool] = []

    def unclean_once(question_id: str, state: Mapping[str, Any]) -> dict[str, Any]:
        if question_id == "keyframe_clean" and not spent:
            spent.append(True)
            return {"kind": "noul", "noul": 0.02}
        return demo_answer(question_id, state)

    media = FakeMediaProvider()
    result, reviews = _run(video_config, media, decisions=FakeDecisionProvider(unclean_once))

    assert media.calls.count("image") == 7
    assert reviews[0].stage == "storyboard"
    assert reviews[0].required_changes == []
    assert max(asset.attempt for asset in result["keyframes"].values()) == 1


@pytest.mark.video
def test_narration_far_longer_than_planned_is_flagged_not_forced(
    video_config: ContentConfig,
) -> None:
    # The plan sizes its beats at a third of what the script says. The miss is shown to
    # the person; the writer is not forced to cut, because the music adapts.
    def undersized(input_text: str, output_type: type[BaseModel]) -> Any:
        response = demo_response(input_text, output_type)
        if output_type is not EditorialBrief:
            return response
        brief = EditorialBrief.model_validate(response)
        arc = [phase.model_copy(update={"words": phase.words // 3}) for phase in brief.arc]
        return brief.model_copy(update={"arc": arc})

    _, reviews = _run(
        video_config,
        FakeMediaProvider(),
        provider=FakeModelProvider(default_factory=undersized),
        action="stop",
    )

    assert reviews[0].stage == "storyboard"
    assert any(
        re.match(r"The narration is predicted to run \d+ s against a planned \d+ s: cut", f)
        for f in reviews[0].findings
    )


@pytest.mark.video
def test_storyboard_feedback_revises_scenes_without_repaying_for_unchanged_ones(
    video_config: ContentConfig,
) -> None:
    provider = FakeModelProvider(default_factory=demo_response)
    media = FakeMediaProvider()
    answers = iter(
        [
            ReviewResponse(action="revise", feedback="S2: make it feel colder."),
            ReviewResponse(action="approve"),
            ReviewResponse(action="approve"),
        ]
    )

    result, reviews = _run(video_config, media, provider=provider, respond=lambda _: next(answers))

    assert [review.stage for review in reviews] == ["storyboard", "storyboard", "final_cut"]
    assert sum(call.output_type is VisualPackage for call in provider.calls) == 2
    # The fake director returns the same storyboard, so every keyframe is reused.
    assert media.calls.count("image") == 6
    assert result["status"] == "approved"


def test_hard_cuts_are_detected_but_gradual_morphs_are_not(tmp_path: Path) -> None:
    cut = tmp_path / "cut.mp4"
    ffmpeg.run(
        "-f", "lavfi", "-i", "color=c=red:s=320x568:d=1", "-f", "lavfi",
        "-i", "color=c=blue:s=320x568:d=1", "-filter_complex", "[0][1]concat=n=2:v=1",
        "-pix_fmt", "yuv420p", cut,
    )  # fmt: skip
    morph = tmp_path / "morph.mp4"
    ffmpeg.run(
        "-f", "lavfi", "-i", "color=c=red:s=320x568:d=2", "-f", "lavfi",
        "-i", "color=c=blue:s=320x568:d=2",
        "-filter_complex", "[0][1]xfade=transition=fade:duration=1.8:offset=0.1",
        "-pix_fmt", "yuv420p", morph,
    )  # fmt: skip

    assert [round(time) for time in hard_cuts(cut, threshold=10)] == [1]
    assert hard_cuts(morph, threshold=10) == []


def _run(
    config: ContentConfig,
    media: FakeMediaProvider,
    *,
    decisions: FakeDecisionProvider | None = None,
    provider: FakeModelProvider | None = None,
    duration_seconds: int | None = None,
    action: str = "approve",
    respond: Any = None,
    source: FakeImageSource | None = None,
    stop_at_listen: bool = False,
    renderer: FakeBlender | None = None,
) -> tuple[ContentOutput, list[ReviewRequest]]:
    graph = build_graph(
        config=config,
        providers={"fake": provider or FakeModelProvider(default_factory=demo_response)},
        decision_provider=decisions or FakeDecisionProvider(demo_answer),
        media_provider=media,
        image_sources=[source or FakeImageSource()],
        checkpointer=create_checkpointer(),
        renderer=renderer,
    )
    initial = create_initial_state(
        "The Great Stink",
        source_material=None,
        user_instructions=None,
        config=config,
        duration_seconds=duration_seconds,
    )
    runtime: RunnableConfig = {"configurable": {"thread_id": f"production-{id(media)}"}}
    result = cast(dict[str, Any], graph.invoke(initial, runtime))
    reviews: list[ReviewRequest] = []
    while result.get("__interrupt__"):
        request = ReviewRequest.model_validate(result["__interrupt__"][0].value)
        if request.stage == "listen" and not stop_at_listen:
            # Tests script the reviews that follow; the narration is approved as heard.
            response = ReviewResponse(action="approve")
            result = cast(
                dict[str, Any],
                graph.invoke(Command[Any](resume=response.model_dump()), runtime),
            )
            continue
        reviews.append(request)
        response = (
            respond(request) if respond else ReviewResponse.model_validate({"action": action})
        )
        result = cast(
            dict[str, Any], graph.invoke(Command[Any](resume=response.model_dump()), runtime)
        )
    return cast(ContentOutput, result), reviews


def test_the_narration_is_heard_before_any_picture_is_paid_for(
    video_config: ContentConfig,
) -> None:
    media = FakeMediaProvider()

    _, reviews = _run(video_config, media, action="stop", stop_at_listen=True)

    assert reviews[0].stage == "listen"
    assert "image" not in media.calls and "speech" in media.calls
    assert reviews[0].attachments[0].endswith(".m4a")
    assert "wpm target" in reviews[0].snapshot

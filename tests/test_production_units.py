import json
import shutil
from pathlib import Path
from typing import Any, cast

import pytest

from content.config import load_config
from content.production import ffmpeg
from content.production.assemble import (
    Framing,
    dissolve_join,
    glide,
    landing,
    mix_audio,
    motion_clip,
    music_bed,
    texture,
)
from content.production.audition import audition, design_voices
from content.production.budget import (
    Pricing,
    morph_timings,
    past_averages,
    project,
    scene_allowance,
    spent,
)
from content.production.checks import (
    integrated_loudness,
    listen_issues,
    measure,
    tone_issues,
    word_error_rate,
)
from content.production.media import (
    PNG_SIGNATURE,
    FakeMediaProvider,
    GenerationRefused,
    OpenRouterMediaProvider,
    _directed,
    as_png,
)
from content.production.producer import Producer
from content.production.subtitles import align, chunk, to_ass
from content.production.timing import lay_out, passage_starts, scene_timings
from content.production.voice_lock import lock_voice
from content.providers.base import Usage
from content.providers.cache import AssetCache
from content.providers.images import WikimediaCommons
from content.schemas.media import NarrationClip, SceneTiming, Word
from content.schemas.script import ScriptPackage
from content.schemas.visuals import Scene
from content.state import ContentState
from content.theme import (
    BreathSpec,
    CameraFraming,
    CameraMove,
    TextureSpec,
    Theme,
    VoiceDesign,
    load_theme,
)
from content.workflow.demo import demo_response

THEME = load_theme(Path(__file__).parents[1] / "themes/starter")


def test_scene_windows_follow_the_words_actually_spoken() -> None:
    # Two passages: U1 and U2 spoken in one take, then U3 after a breath.
    first = _clip(
        "P1",
        ["U1", "U2"],
        7.0,
        [
            ("The", 0.0, 0.6),
            ("harbour.", 0.6, 1.4),
            ("Nobody", 3.1, 3.6),
            ("said.", 3.6, 6.8),
        ],
    )
    second = _clip("P2", ["U3"], 5.0, [("Money.", 0.0, 4.9)])
    texts = {"U1": "The harbour.", "U2": "Nobody said.", "U3": "Money."}
    starts = passage_starts([first, second], [0.5], lead=1.0)

    windows, words = lay_out([first, second], starts, texts)

    assert starts == [1.0, 8.5]
    assert windows == {"U1": (1.0, 2.4), "U2": (4.1, 8.0), "U3": (8.5, 13.5)}
    assert [word.text for word in words] == ["The", "harbour.", "Nobody", "said.", "Money."]


def test_scenes_run_from_their_first_word_to_the_next_scene() -> None:
    windows = {"U1": (0.0, 3.0), "U2": (3.5, 7.5), "U3": (8.0, 13.0), "U4": (13.5, 30.0)}
    scenes = [_scene("S1", ["U1", "U2"]), _scene("S2", ["U3"]), _scene("S3", ["U4"])]

    timings = scene_timings(scenes, windows, 31.0)

    assert [(t.scene_id, t.start, t.end) for t in timings] == [
        ("S1", 0.0, 8.0),
        ("S2", 8.0, 13.5),
        ("S3", 13.5, 31.0),
    ]


def test_every_join_morphs_taking_time_from_both_sides() -> None:
    scenes = [
        SceneTiming(scene_id="S1", start=0.0, end=10.0),
        SceneTiming(scene_id="S2", start=10.0, end=13.0),
        SceneTiming(scene_id="S3", start=13.0, end=30.0),
    ]

    morphs = morph_timings(scenes, 4.0)

    # A 4 s morph takes 2 s from each side, but never more than a third of a scene, so the
    # short S2 is still seen held for a second between its two morphs.
    assert [(t.from_scene_id, t.to_scene_id, t.start, t.seconds) for t in morphs] == [
        ("S1", "S2", 8.0, 3.0),
        ("S2", "S3", 12.0, 3.0),
    ]


def test_the_budget_left_after_the_writing_sets_how_many_scenes_there_are() -> None:
    pricing = Pricing(cap=5.0, image_usd=0.05, video_usd_per_second=0.03, morph_seconds=4)

    scenes = scene_allowance(2.0, pricing)

    assert scenes == 11
    assert project(scenes, 2.0, pricing).projected <= 5.0
    assert project(scenes + 1, 2.0, pricing).projected > 5.0 - 0.3
    assert scene_allowance(4.9, pricing) == 0


def test_the_cost_so_far_fills_unpriced_calls_from_past_runs(tmp_path: Path) -> None:
    log = tmp_path / "old.run.json"
    log.write_text(
        '{"calls": [{"operation": "image", "cost_usd": 0.04}, '
        '{"operation": "image", "cost_usd": 0.06}]}',
        encoding="utf-8",
    )
    calls = [
        {"operation": "image", "cost_usd": None},
        {"operation": "chat", "cost_usd": 0.5},
    ]

    assert spent(calls, past_averages([log])) == pytest.approx(0.55)  # type: ignore[arg-type]


def test_subtitles_show_script_words_with_heard_timings() -> None:
    heard = [
        Word(text="The", start=0.0, end=0.2),
        Word(text="B.", start=0.2, end=0.4),
        Word(text="B.", start=0.4, end=0.6),
        Word(text="C.", start=0.6, end=0.8),
        Word(text="filmed", start=0.8, end=1.2),
        Word(text="it.", start=1.2, end=1.6),
    ]

    words = align("The BBC filmed it.", heard, start=10.0, end=12.0)

    assert [(w.text, w.start) for w in words] == [
        ("The", 10.0),
        ("BBC", 10.2),
        ("filmed", 10.8),
        ("it.", 11.2),
    ]
    evenly = align("One two three four", [], start=0.0, end=2.0)
    assert [w.start for w in evenly] == [0.0, 0.5, 1.0, 1.5]


def test_ass_uses_theme_font_colours_and_word_highlight() -> None:
    spec = THEME.spec.subtitles
    words = align("The operation began in secret.", [], start=0.0, end=2.5)
    phrases = chunk(words, spec)

    ass = to_ass(phrases, spec, 1080, 1920)

    assert [[w.text for w in phrase] for phrase in phrases] == [
        ["The", "operation", "began"],
        ["in", "secret."],
    ]
    assert "Style: Main,Archivo Black,78,&H00D6E1E6,&H0035D3F2,&H000A0707" in ass
    assert "PlayResY: 1920" in ass
    assert "{\\c&H0035D3F2}THE{\\r} OPERATION BEGAN" in ass
    assert ass.count("Dialogue:") == 5


def test_subtitle_phrases_never_overlap_on_screen() -> None:
    # Aligned timings can run past the next phrase's start, and libass stacked two lines.
    words = [
        Word(text="own", start=0.0, end=0.4),
        Word(text="records,", start=0.4, end=1.1),
        Word(text="it", start=0.9, end=1.0),
        Word(text="said", start=1.0, end=1.3),
    ]
    ass = to_ass(chunk(words, THEME.spec.subtitles), THEME.spec.subtitles, 1080, 1920)

    def seconds(stamp: str) -> float:
        hours, minutes, rest = stamp.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(rest)

    events = [
        (seconds(line.split(",")[1]), seconds(line.split(",")[2]))
        for line in ass.splitlines()
        if line.startswith("Dialogue:")
    ]
    pairs = zip(events, events[1:], strict=False)
    assert all(end <= following for (_, end), (following, _) in pairs)


def test_word_error_rate_counts_substitutions_and_omissions() -> None:
    assert word_error_rate("the machines were weakened", "the machines were weakened") == 0
    assert word_error_rate("the machines were weakened", "the machine was weakened") == 0.5


def test_cache_pays_once_for_identical_requests(tmp_path: Path) -> None:
    cache = AssetCache(tmp_path)
    produced: list[str] = []

    def produce() -> tuple[bytes, Usage]:
        produced.append("paid")
        return b"image", Usage(model="m", cost_usd=0.04)

    first, usage = cache.fetch("keyframe", {"prompt": "a", "seed": 1}, ".png", produce)
    again, repeat_usage = cache.fetch("keyframe", {"seed": 1, "prompt": "a"}, ".png", produce)
    other, _ = cache.fetch("keyframe", {"prompt": "b", "seed": 1}, ".png", produce)

    assert first == again != other
    assert usage is not None and usage.cost_usd == 0.04
    assert repeat_usage is None
    assert produced == ["paid", "paid"]
    assert first.read_bytes() == b"image"


def _clip(
    passage_id: str, unit_ids: list[str], duration: float, heard: list[tuple[str, float, float]]
) -> NarrationClip:
    return NarrationClip(
        passage_id=passage_id,
        unit_ids=unit_ids,
        spoken_text="",
        words_per_minute=160,
        tempo=1.0,
        path="",
        duration=duration,
        heard=[Word(text=text, start=start, end=end) for text, start, end in heard],
        issues=[],
    )


def _scene(scene_id: str, units: list[str]) -> Scene:
    return Scene.model_validate(
        {
            "scene_id": scene_id,
            "script_unit_ids": units,
            "purpose": "p",
            "visual_function": "show",
            "evidence_presentation": "symbolic",
            "anchor": {
                "subject": "s",
                "setting": "t",
                "composition": "c",
                "key_elements": [],
                "light_and_colour": "l",
            },
            "camera": "push_in",
            "motion": "m",
            "morph_bridge": "b",
        }
    )


def test_images_returned_as_jpeg_are_storedas_png(tmp_path: Path) -> None:
    jpeg = tmp_path / "frame.jpg"
    ffmpeg.run("-f", "lavfi", "-i", "color=c=red:s=64x64:d=1", "-frames:v", "1", jpeg)

    png = as_png(jpeg.read_bytes())

    assert png.startswith(PNG_SIGNATURE)
    assert as_png(png) == png


def test_bright_saturated_keyframes_fail_the_tone_check(tmp_path: Path) -> None:
    neon, ink = tmp_path / "neon.png", tmp_path / "ink.png"
    ffmpeg.run("-f", "lavfi", "-i", "color=c=0xE0236F:s=90x160", "-frames:v", "1", neon)
    ffmpeg.run("-f", "lavfi", "-i", "color=c=0x1C1C22:s=90x160", "-frames:v", "1", ink)
    limits = {"max_mean_brightness": 55, "max_highlight_saturation": 26}

    assert tone_issues(measure(ink), **limits) == []
    issues = tone_issues(measure(neon), **limits)
    assert any(issue.startswith("too bright") for issue in issues)
    assert any(issue.startswith("colour too saturated") for issue in issues)


def test_the_mix_lands_on_the_loudness_target(tmp_path: Path) -> None:
    voice, music, mix = tmp_path / "voice.wav", tmp_path / "music.wav", tmp_path / "mix.m4a"
    ffmpeg.run("-f", "lavfi", "-i", "sine=frequency=220:duration=6", "-af", "volume=-20dB", voice)
    ffmpeg.run("-f", "lavfi", "-i", "anoisesrc=color=pink:duration=3", music)

    mix_audio(voice, music, THEME.spec.music, mix)

    assert integrated_loudness(mix) == pytest.approx(THEME.spec.music.loudness_lufs, abs=0.5)


def test_the_locked_music_track_is_looped_and_trimmed_to_the_video(tmp_path: Path) -> None:
    track, bed = tmp_path / "track.wav", tmp_path / "bed.wav"
    ffmpeg.run("-f", "lavfi", "-i", "anoisesrc=color=brown:duration=10", track)

    music_bed(track, 26.5, bed)

    assert ffmpeg.probe(bed).duration == pytest.approx(26.5, abs=0.05)


def test_directions_reach_each_provider_in_its_documented_form() -> None:
    assert _directed("Hello.", "brisk", "openai") == {
        "provider": {"options": {"openai": {"instructions": "brisk"}}}
    }
    assert _directed("Hello.", "brisk", "google") == {
        "provider": {"options": {"google-ai-studio": {"speech_metadata": {"style": "brisk"}}}}
    }
    assert _directed("Hello.", "brisk", "inline") == {"input": "[brisk] Hello."}
    assert _directed("Hello.", "brisk", "none") == {}


def test_voice_audition_renders_directable_voices_with_and_without_direction(
    tmp_path: Path,
) -> None:
    candidates = THEME.spec.voice.candidates
    # Cloning candidates render only once the theme has a master recording to clone.
    cloning = THEME.reference_audio is not None
    expected = sum(
        1 if c.direction_style == "none" else 2 for c in candidates if cloning or not c.clone
    )

    results = audition(THEME, FakeMediaProvider(), tmp_path)
    clips = [line for line in results if Path(line).is_file()]

    assert len(clips) == expected
    assert len(results) - len(clips) == (0 if cloning else sum(c.clone for c in candidates))
    assert any("__directed." in clip for clip in clips)


def test_designed_voices_are_rendered_with_their_descriptions(tmp_path: Path) -> None:
    design = VoiceDesign(
        model="bytedance-seed/seed-audio-1-0",
        voice=None,
        direction_style="inline",
        description="A warm, low narrator in her forties, unhurried and precise.",
    )
    voice = THEME.spec.voice.model_copy(update={"designs": [design, design]})
    theme = Theme(THEME.root, THEME.spec.model_copy(update={"voice": voice}), THEME.skill)

    results = design_voices(theme, FakeMediaProvider(), tmp_path)

    assert len(results) == 2
    sidecar = json.loads((tmp_path / "design-1.json").read_text())
    assert sidecar["description"] == design.description


def test_locking_a_voice_stores_the_master_and_needs_no_calibration(tmp_path: Path) -> None:
    shutil.copytree(THEME.root, tmp_path / "theme")
    theme = load_theme(tmp_path / "theme")
    clip = tmp_path / "chosen.mp3"
    ffmpeg.run("-f", "lavfi", "-i", "sine=frequency=180:duration=4", clip)

    master = lock_voice(
        theme,
        clip,
        transcript="The passage the clip reads.",
        model="fish-audio/s2.1-pro",
        voice=None,
        direction_style="inline",
    )

    locked = load_theme(tmp_path / "theme").spec.voice
    assert locked.model == "fish-audio/s2.1-pro"
    assert locked.reference_audio == "voice/master.mp3"
    assert master.is_file()
    # Clones of the master are auditioned once it exists.
    clips = audition(load_theme(tmp_path / "theme"), FakeMediaProvider(), tmp_path / "audition")
    assert any("__master" in clip for clip in clips)


def test_a_rate_limited_request_waits_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __init__(self, status: int) -> None:
            self.status_code, self.text = status, ""
            self.headers: dict[str, str] = {}

    class Http:
        def __init__(self) -> None:
            self.statuses = [429, 503, 200]

        def post(self, path: str, json: object) -> Response:
            return Response(self.statuses.pop(0))

    waits: list[float] = []
    monkeypatch.setattr("content.production.media.time.sleep", waits.append)
    media = OpenRouterMediaProvider(http=Http(), chat=object())

    assert media._post("/audio/speech", {}).status_code == 200
    assert len(waits) == 2


def test_a_rate_limited_reference_download_waits_and_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        def __init__(self, status: int) -> None:
            self.status_code, self.content = status, b"image"
            self.headers = {"retry-after": "3"} if status == 429 else {}

        def raise_for_status(self) -> None:
            assert self.status_code == 200

    class Http:
        def __init__(self) -> None:
            self.statuses = [429, 429, 200]

        def get(self, url: str, params: object = None) -> Response:
            return Response(self.statuses.pop(0))

    waits: list[float] = []
    monkeypatch.setattr("content.providers.images.time.sleep", waits.append)

    assert WikimediaCommons(http=Http()).download("https://upload.example/x.jpg") == b"image"
    assert waits == [3.0, 3.0]


def test_a_glide_ends_on_the_focal_point() -> None:
    # A fixed pan once drifted toward a corner; the camera now heads for the named focus.
    focal = (0.516, 0.42)
    push_in = CameraMove(
        describe="a slow push-in",
        start=CameraFraming(zoom=1.06, toward_centre=0.5),
        end=CameraFraming(zoom=1.24),
    )

    start, end = glide(push_in, focal)

    assert landing(focal, end) == pytest.approx((0.5, 0.5), abs=0.01)
    assert start.x == pytest.approx(0.508) and start.y == pytest.approx(0.46)


def test_every_theme_camera_move_keeps_the_focal_point_in_view() -> None:
    for name, move in THEME.spec.visual.camera_moves.items():
        for framing in glide(move, (0.3, 0.7)):
            x, y = landing((0.3, 0.7), framing)
            assert 0 < x < 1 and 0 < y < 1, name


def test_the_view_never_leaves_the_picture() -> None:
    # A focal point near the top edge: the view stops at the edge, so the point sits high.
    x, y = landing((0.5, 0.05), Framing(1.25, 0.5, 0.05))
    assert x == pytest.approx(0.5)
    assert y == pytest.approx(0.0625)


def test_a_refused_render_is_remembered_and_never_paid_for_twice(tmp_path: Path) -> None:
    cache = AssetCache(tmp_path)
    attempts: list[str] = []

    def refuse() -> tuple[bytes, Usage]:
        attempts.append("paid")
        raise GenerationRefused("input image violates usage guidelines")

    for _ in range(2):
        with pytest.raises(GenerationRefused, match="usage guidelines"):
            cache.fetch("segment", {"attempt": 0}, ".mp4", refuse, refusal=GenerationRefused)

    assert attempts == ["paid"]


def test_a_fragment_is_flagged_only_where_the_voice_stopped() -> None:
    script = "Ada Lovelace, the poet's daughter, wrote the notes."
    stopped = [
        Word(text="Ada", start=0.0, end=0.3),
        Word(text="Lovelace,", start=0.3, end=0.7),
        Word(text="the", start=0.75, end=0.85),
        Word(text="poet's", start=0.85, end=1.3),
        Word(text="daughter.", start=1.3, end=1.8),
        Word(text="Wrote", start=2.3, end=2.5),
        Word(text="the", start=2.5, end=2.6),
        Word(text="notes.", start=2.6, end=3.0),
    ]
    # The transcriber's full stop with no pause after it: a guess, not a stop.
    flowing = [
        word.model_copy(update={"start": word.start - 0.45, "end": word.end - 0.45})
        if index >= 5
        else word
        for index, word in enumerate(stopped)
    ]

    assert any("stopped after" in issue for issue in listen_issues("P1", script, stopped))
    assert not any("stopped after" in issue for issue in listen_issues("P1", script, flowing))


def test_a_texture_with_every_layer_off_still_renders(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    ffmpeg.run("-f", "lavfi", "-i", "color=c=gray:s=90x160:d=1", "-pix_fmt", "yuv420p", clip)
    off = TextureSpec(fractal=0, vignette_swing=0, fringe_pixels=0, grain=0, flicker=0)
    on = THEME.spec.visual.motion.texture

    for name, spec in (("off", off), ("on", on)):
        output = texture(clip, tmp_path / f"{name}.mp4", spec=spec, breath_seconds=5.5, fps=25)
        assert ffmpeg.probe(output).duration == pytest.approx(1.0, abs=0.1)


def test_tinted_ripples_take_on_the_scenes_colour_faintly(tmp_path: Path) -> None:
    still = tmp_path / "still.png"
    ffmpeg.run("-f", "lavfi", "-i", "color=c=gray:s=180x320", "-frames:v", "1", still)
    breath = BreathSpec(seconds=2.0, swell=0.0, ripple_pixels=5, tint=0.3)
    framing = Framing(1.0, 0.5, 0.5)

    def mean_rgb(tint: tuple[str, float] | None, name: str) -> tuple[float, float, float]:
        clip = motion_clip(
            still, 2.0, framing, framing, (0.5, 0.5), tmp_path / f"{name}.mp4",
            breath=breath, width=90, height=160, fps=10, tint=tint,
        )  # fmt: skip
        raw = ffmpeg.run(
            "-ss", "1", "-i", clip, "-frames:v", "1", "-vf", "scale=9:16",
            "-f", "rawvideo", "-pix_fmt", "rgb24", tmp_path / f"{name}.rgb",
        )  # fmt: skip
        del raw
        data = (tmp_path / f"{name}.rgb").read_bytes()
        return tuple(sum(data[i::3]) / (len(data) / 3) for i in range(3))  # type: ignore[return-value]

    plain = mean_rgb(None, "plain")
    red = mean_rgb(("#FF0000", 0.3), "red")

    # The crests lean red; the grey picture underneath stays recognisably grey.
    assert red[0] - red[2] > plain[0] - plain[2] + 3
    assert abs(red[1] - plain[1]) < 40


def test_a_dissolve_after_clips_that_meet_frame_to_frame_still_joins(tmp_path: Path) -> None:
    # A still meets its morph frame to frame; the next still dissolves in (a dropped scene).
    clips = []
    for name, colour in (("still", "gray"), ("morph", "white"), ("next", "black")):
        clip = tmp_path / f"{name}.mp4"
        ffmpeg.run("-f", "lavfi", "-i", f"color=c={colour}:s=90x160:d=1:r=10", "-pix_fmt",
                   "yuv420p", clip)  # fmt: skip
        clips.append((clip, 1.0))

    output = dissolve_join(clips, tmp_path / "cut.mp4", joins=[0.0, 0.5, 0.0], fps=10)

    assert ffmpeg.probe(output).duration == pytest.approx(3.0, abs=0.15)


def test_a_failed_render_leaves_no_file_to_be_mistaken_for_a_finished_one(tmp_path: Path) -> None:
    output = tmp_path / "broken.mp4"

    with pytest.raises(ffmpeg.FfmpegError):
        ffmpeg.run("-f", "lavfi", "-i", "color=c=gray:s=90x160:d=1", "-vf", "nosuchfilter", output)

    assert not output.exists()


def test_a_note_on_one_passage_records_only_that_passage(project_root: Path) -> None:
    config = load_config(project_root / "config/config.fake-video.json")
    assert config.production is not None
    voice = config.theme.spec.voice.model_copy(update={"direction_style": "inline"})
    theme = Theme(
        config.theme.root,
        config.theme.spec.model_copy(update={"voice": voice}),
        config.theme.skill,
    )
    producer = Producer(
        config=config.production,
        theme=theme,
        media=FakeMediaProvider(),
        judge=cast(Any, None),
        image_sources=[],
    )
    script = ScriptPackage.model_validate(demo_response(json.dumps({"topic": "x"}), ScriptPackage))
    state = cast(ContentState, {"script_package": script, "narration": {}})
    recorded = {}
    for send in cast(list[Any], producer.narration.narration_tasks(state)):
        task = send.arg
        recorded[task["passage_id"]] = NarrationClip(
            passage_id=task["passage_id"],
            unit_ids=task["unit_ids"],
            spoken_text=task["spoken_text"],
            words_per_minute=task["words_per_minute"],
            direction=task["direction"],
            first_take=task["first_take"],
            tempo=1.0,
            path="unused.wav",
            duration=1.0,
            heard=[],
            issues=[],
        )
    first, second = list(recorded)[:2]
    state["narration"] = recorded
    assert producer.narration.narration_tasks(state) == "time_scenes"

    state["passage_directions"] = {first: "a beat before the number"}
    state["retakes_asked"] = {second: 1}
    again = {
        send.arg["passage_id"]: send.arg
        for send in cast(list[Any], producer.narration.narration_tasks(state))
    }

    assert set(again) == {first, second}
    assert again[first]["direction"].endswith("; a beat before the number")
    assert again[second]["first_take"] == voice.retakes + 1

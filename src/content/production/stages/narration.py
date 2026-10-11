"""The narration is the clock: each passage recorded and paced, then the scenes timed to the
music around it."""

import json
import math
from pathlib import Path

from langgraph.types import Send

from content.production import assemble, checks
from content.production.budget import (
    morph_timings,
    project,
)
from content.production.score import (
    arranged_beats,
    arrangements,
    fit,
    land,
    on_beat,
    spans,
    turn_unit,
)
from content.production.studio import (
    NarrationTask,
    Studio,
    decision,
    required,
)
from content.production.subtitles import chunk, to_ass
from content.production.timing import lay_out, passage_starts, scene_timings
from content.providers import ffmpeg
from content.providers.base import Usage
from content.providers.cache import file_digest
from content.schemas.media import (
    NarrationClip,
    Timeline,
    Word,
)
from content.state import CallRecord, ContentState
from content.story.pace import gaps, passages
from content.theme import narration_direction

# Share of script words the narration may get wrong before a person is told.
MAX_NARRATION_WORD_ERROR = 0.2

# Spare seconds in the chosen edit of the music: at most this much is added to each
# breath between passages, and at most this much music plays before the first word.
MAX_EXTRA_BREATH_SECONDS = 0.4

MAX_LEAD_SECONDS = 1.5


class Narration(Studio):
    def narration_tasks(self, state: ContentState) -> list[Send] | str:
        script = required(state.get("script_package"), "a script")
        current = state.get("narration", {})
        voice = self.theme.spec.voice
        tasks = []
        phases = {unit.unit_id: unit.arc_phase_id for unit in script.script_units}
        asked, retakes = state.get("passage_directions", {}), state.get("retakes_asked", {})
        for index, passage in enumerate(
            passages(script.script_units, self.theme.speaker(script.voice_direction))
        ):
            rate = voice.words_per_minute * (voice.hook_pace if index == 0 else 1.0)
            direction = narration_direction(
                self.theme, script.voice_direction, phases[passage.unit_ids[0]]
            )
            if direction is not None and passage.passage_id in asked:
                direction = f"{direction}; {asked[passage.passage_id]}"
            first_take = retakes.get(passage.passage_id, 0) * (voice.retakes + 1)
            clip = current.get(passage.passage_id)
            wanted = (passage.text, rate, direction, first_take)
            if (
                clip is None
                or (
                    clip.spoken_text,
                    clip.words_per_minute,
                    clip.direction,
                    clip.first_take,
                )
                != wanted
            ):
                tasks.append(
                    Send(
                        "narrate_passage",
                        NarrationTask(
                            passage_id=passage.passage_id,
                            unit_ids=passage.unit_ids,
                            spoken_text=passage.text,
                            words_per_minute=rate,
                            direction=direction,
                            first_take=first_take,
                        ),
                    )
                )
        return tasks or "time_scenes"

    def narrate_passage(self, state: NarrationTask) -> ContentState:
        """One take for the whole passage, so the narrator's own phrasing carries it from
        sentence to sentence; then the take is measured and brought towards the passage's
        rate, no further than `tempo_range` allows, since the voice model's speed varies
        widely from take to take (docs/narration.md). One take is the rule: it is recorded
        again, up to `retakes` times, only when it falls short of the pace the script was
        sized at (`VoiceSpec.rate`) by more than the length tolerance. The take needing
        the least adjustment is kept: a heavy stretch is what makes a passage lurch."""
        voice = self.theme.spec.voice
        low, high = voice.tempo_range
        floor = (state["words_per_minute"] * voice.rate / voice.words_per_minute) * (
            1 - voice.length_tolerance
        )
        calls: list[CallRecord] = []
        takes: list[tuple[Path, float]] = []
        for take in range(voice.retakes + 1):
            raw, natural, take_calls = self._take(
                state["spoken_text"], state["first_take"] + take, state["direction"]
            )
            calls += take_calls
            takes.append((raw, natural))
            if natural * min(max(state["words_per_minute"] / natural, low), high) >= floor:
                break
        raw, natural = min(
            takes, key=lambda pair: abs(math.log(state["words_per_minute"] / pair[1]))
        )
        tempo = round(min(max(state["words_per_minute"] / natural, low), high), 3)
        clip = self.derived("speech", [file_digest(raw), f"{tempo:.3f}"], ".wav")
        if not clip.is_file():
            assemble.spoken_clip(raw, clip, tempo=tempo)

        def transcribe() -> tuple[bytes, Usage]:
            words, usage = self.media.transcribe(model=self.config.transcription_model, audio=clip)
            return json.dumps([word.model_dump() for word in words]).encode(), usage

        transcript, transcription_calls = self.fetch(
            "transcript",
            {"model": self.config.transcription_model, "audio": file_digest(clip)},
            ".json",
            "transcription",
            transcribe,
            about="transcript of a narration take",
        )
        heard = [Word.model_validate(word) for word in json.loads(transcript.read_text())]
        issues = []
        if tempo in (low, high):
            issues.append(
                f"{state['passage_id']}: read slowly on all {len(takes)} takes; even at the "
                f"{tempo:.2f}× limit it runs at {natural * tempo:.0f} words a minute, not "
                f"{state['words_per_minute']:.0f}, so it may drag."
            )
        issues += checks.listen_issues(state["passage_id"], state["spoken_text"], heard)
        if heard:
            error = checks.word_error_rate(state["spoken_text"], " ".join(w.text for w in heard))
            if error > MAX_NARRATION_WORD_ERROR:
                issues.append(
                    f"{state['passage_id']}: the narration differs from the script "
                    f"({error:.0%} of words)."
                )
        narration = NarrationClip(
            passage_id=state["passage_id"],
            unit_ids=state["unit_ids"],
            spoken_text=state["spoken_text"],
            words_per_minute=state["words_per_minute"],
            direction=state["direction"],
            first_take=state["first_take"],
            tempo=tempo,
            path=str(clip),
            duration=ffmpeg.probe(clip).duration,
            heard=heard,
            issues=issues,
        )
        return {
            "narration": {state["passage_id"]: narration},
            "call_log": [*calls, *transcription_calls],
        }

    def _take(
        self, text: str, take: int, direction: str | None
    ) -> tuple[Path, float, list[CallRecord]]:
        """One recording of a passage and the rate it was spoken at, silences trimmed.
        The first take keeps its original cache key, so takes already paid for are reused."""
        voice = self.theme.spec.voice
        reference = self.theme.reference_audio
        request = {
            "model": voice.model,
            "voice": voice.voice,
            "reference": file_digest(reference) if reference else None,
            "text": text,
            "direction": direction,
        }
        raw, calls = self.fetch(
            "speech",
            request if take == 0 else {**request, "take": take},
            ".audio",
            "narration",
            lambda: self.media.speech(
                model=voice.model,
                text=text,
                voice=voice.voice,
                reference_audio=reference,
                reference_transcript=voice.reference_transcript,
                direction=direction,
                direction_style=voice.direction_style,
            ),
            about=f"narration take {take}: {text}",
        )
        untouched = self.derived("speech", [file_digest(raw), "1.000"], ".wav")
        if not untouched.is_file():
            assemble.spoken_clip(raw, untouched, tempo=1.0)
        return raw, len(text.split()) / ffmpeg.probe(untouched).duration * 60, calls

    def time_scenes(self, state: ContentState) -> ContentState:
        """Fit the music to the spoken narration, lay it on one timeline, time the scenes
        from the words actually spoken, and subtitle it.

        The shortest edit of the music that holds the narration is used. Spare seconds go
        to the breaths between passages, then a short lead-in; the rest lets the track
        play out. Passage starts are then moved (never the speech inside them) so the turn
        lands on the peak and each passage starts on a beat."""
        script = required(state.get("script_package"), "a script")
        visuals = required(state.get("visual_package"), "a storyboard")
        voice = self.theme.spec.voice
        spoken = passages(script.script_units, self.theme.speaker(script.voice_direction))
        narration = state.get("narration", {})
        clips = [narration.get(passage.passage_id) for passage in spoken]
        if any(
            clip is None or clip.spoken_text != passage.text
            for clip, passage in zip(clips, spoken, strict=True)
        ):
            raise ValueError("Timing requires narration for the current script")
        clips_now = [clip for clip in clips if clip is not None]
        durations = [clip.duration for clip in clips_now]
        breaths = gaps([passage.transition for passage in spoken], voice)
        speech = sum(durations) + sum(breaths) + voice.tail_seconds

        music = self.music_map()
        outro = self.theme.spec.music.outro_seconds
        limit = self.theme.spec.format.max_seconds
        arrangement = fit(music, speech, outro, limit) if music is not None else None
        if music is not None and arrangement is None:
            longest = max(a.seconds for a in arrangements(music, limit)) - outro[0]
            return decision(
                "script",
                "revise_script",
                [
                    f"The narration runs {speech:.0f} s, longer than the longest edit of the "
                    f"music allows ({longest:.0f} s): cut a beat that serves the story least."
                ],
                structural=True,
            )
        lead = 0.0
        if music is not None and arrangement is not None:
            spare = arrangement.seconds - speech - outro[1]
            if spare > 0 and breaths:
                extra = min(spare / len(breaths), MAX_EXTRA_BREATH_SECONDS)
                breaths = [breath + extra for breath in breaths]
                spare -= extra * len(breaths)
            lead = min(max(spare, 0.0), MAX_LEAD_SECONDS)
            turn = turn_unit(script.script_units)
            index = next((i for i, p in enumerate(spoken) if turn in p.unit_ids), 0)
            landed = land(index, durations, breaths, arrangement.peak_at - lead)
            beats = [beat - lead for beat in arranged_beats(music, arrangement)]
            on_grid = on_beat(durations, landed, beats)
            if lead + sum(durations) + sum(on_grid) + voice.tail_seconds + outro[0] <= (
                arrangement.seconds
            ):
                breaths = on_grid
        total = lead + sum(durations) + sum(breaths) + voice.tail_seconds
        video_seconds = arrangement.seconds if arrangement is not None else total

        starts = passage_starts(clips_now, breaths, lead)
        windows, words = lay_out(
            clips_now, starts, {unit.unit_id: unit.text for unit in script.script_units}
        )
        timings = scene_timings(visuals.scenes, windows, total)
        transitions = morph_timings(timings, self.config.transition_seconds)
        budget = project(len(timings), self.spent(state), self.pricing())
        track = self.derived(
            "timeline",
            [f"{clip.path}@{start}" for clip, start in zip(clips_now, starts, strict=True)]
            + [str(video_seconds)],
            ".wav",
        )
        if not track.is_file():
            assemble.narration_track(
                list(zip(clips_now, starts, strict=True)), video_seconds, track
            )
        spec = self.theme.spec
        subtitles_text = to_ass(
            chunk(words, spec.subtitles), spec.subtitles, spec.format.width, spec.format.height
        )
        subtitles = self.derived("subtitles", [subtitles_text], ".ass")
        subtitles.write_text(subtitles_text, encoding="utf-8")
        timeline = Timeline(
            narration_path=str(track),
            subtitles_path=str(subtitles),
            total_seconds=round(video_seconds, 3),
            scenes=timings,
            score=spans(music, arrangement) if music and arrangement else [],
            transitions=transitions,
            passage_starts={
                passage.passage_id: round(start, 3)
                for passage, start in zip(spoken, starts, strict=True)
            },
        )
        # A person hears the narration, scored, before any picture is paid for; unchanged
        # narration they already approved goes straight on.
        heard_before = state.get("listened_narration") == timeline.narration_path
        listening: ContentState = {}
        if not heard_before:
            music_track, music_calls = self.music(timeline, arrangement)
            listening = {
                "listen_mix": str(self.mix(timeline, music_track)),
                "call_log": music_calls,
            }
        return {
            **(
                decision("keyframes", "render", [], structural=False)
                if heard_before
                else decision("listen", "review", [], structural=False)
            ),
            **listening,
            "timeline": timeline,
            "budget": budget,
            "arrangement": arrangement,
        }

"""The final cut: stills and morphs joined, the texture pass, the mix and the subtitles."""

from pathlib import Path

from content.production import assemble, checks, ffmpeg
from content.production.studio import (
    Studio,
    decision,
    required,
)
from content.providers.cache import file_digest
from content.schemas.media import (
    ProductionResult,
    Timeline,
)
from content.state import ContentState

JOIN_TOLERANCE_SECONDS = 0.25


class Assembly(Studio):
    def assemble(self, state: ContentState) -> ContentState:
        timeline = required(state.get("timeline"), "a timeline")
        visuals = required(state.get("visual_package"), "a storyboard")
        segments = {asset.scene_id: asset for asset in self.video_segments(state)}
        music, calls = self.music(timeline, state.get("arrangement"))
        video = self.picture(
            timeline,
            visuals.scenes,
            self.current(state, "keyframes"),
            segments,
            self.fields(state),
        )
        mix = self.mix(timeline, music)
        final = self.derived(
            "final",
            [file_digest(video), file_digest(mix), file_digest(Path(timeline.subtitles_path))],
            ".mp4",
        )
        if not final.is_file():
            assemble.finish(
                video, mix, Path(timeline.subtitles_path), self.theme.font_file.parent, final
            )
        issues = self._final_issues(final, video, timeline)
        result = ProductionResult(
            video_path=str(final),
            narration_path=timeline.narration_path,
            subtitles_path=timeline.subtitles_path,
            music_path=str(music) if music else None,
            contact_sheet_path=state.get("contact_sheet") or "",
            duration=ffmpeg.probe(final).duration,
            scenes=timeline.scenes,
        )
        notes = [*state.get("revision_notes", []), *issues]
        return {
            **decision("final_cut", "review", notes, structural=False),
            "production": result,
            "call_log": calls,
        }

    def _final_issues(self, final: Path, cut: Path, timeline: Timeline) -> list[str]:
        spec = self.theme.spec
        info = ffmpeg.probe(final)
        issues = []
        if abs(info.duration - timeline.total_seconds) > 0.5:
            issues.append(
                f"The cut runs {info.duration:.1f} s; the narration timeline is "
                f"{timeline.total_seconds:.1f} s."
            )
        if (info.width, info.height) != (spec.format.width, spec.format.height):
            issues.append(f"The cut is {info.width}×{info.height}, not the theme's frame size.")
        joins = [timing.start for timing in timeline.scenes[1:]]
        for cut_time in checks.hard_cuts(cut, self.config.hard_cut_threshold):
            if any(abs(cut_time - join) <= JOIN_TOLERANCE_SECONDS for join in joins):
                issues.append(f"The join at {cut_time:.1f} s cuts rather than morphs.")
        return issues

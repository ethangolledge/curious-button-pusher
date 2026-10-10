"""The music comes first, as a producer would edit it; the story fits inside it.

From the mapped bed, code lists the arrangements a producer could make without touching
a phrase: the track as written, shorter versions with whole build phrases taken out, and
longer ones with whole phrases repeated. Every join falls on a bar line, with a one-beat
equal-power crossfade across the downbeat, and the track always keeps its own opening and
its own ending. A requested length picks the nearest arrangement as the plan's
target; once the narration has been spoken, the shortest arrangement that holds it (with
a few seconds for the track to play out) is the one used.

The narration then meets the music loosely, a passage at a time: each passage starts on a
beat, and the passage with the turn is moved onto the first bar of the peak when it is
already close. The breaths between passages absorb the moves; inside a passage the
narrator's own timing is never touched.
"""

from collections.abc import Sequence
from pathlib import Path

from content.production import ffmpeg
from content.production.music_map import MusicMap
from content.schemas.media import Arrangement, ScoreSpan
from content.schemas.script import ScriptUnit

# How far a line's start may move to land on a beat.
MAX_NUDGE_SECONDS = 0.25
# The shortest silence allowed between two lines after landing on the beat.
MIN_GAP_SECONDS = 0.05
# How far the reveal may be moved to land on the peak's first bar.
MAX_LANDING_SECONDS = 1.5


def arrangements(music: MusicMap, longest: float) -> list[Arrangement]:
    """Every clean edit no longer than `longest` (the theme's longest video): the track as
    written, then fewer build phrases, then more (repeating the builds and the peak in
    turn), shortest first."""
    order = list(range(len(music.sections)))
    builds = [i for i in order if music.sections[i].label == "build"]
    peak = next(i for i in order if music.sections[i].label == "peak")
    options = [order]
    for dropped in range(1, len(builds) + 1):
        options.append([i for i in order if i not in builds[-dropped:]])
    repeatable = [*builds, peak]
    longer = list(order)
    count = 0
    while _arrange(music, longer).seconds <= longest:
        chosen = repeatable[-1 - count % len(repeatable)]
        at = longer.index(chosen)
        longer = [*longer[: at + 1], chosen, *longer[at + 1 :]]
        options.append(list(longer))
        count += 1
    edits = (_arrange(music, phrases) for phrases in options)
    return sorted((a for a in edits if a.seconds <= longest), key=lambda a: a.seconds)


def choose(
    music: MusicMap, requested: float, outro: tuple[float, float], longest: float
) -> Arrangement:
    """The arrangement whose length best holds a narration of `requested` seconds with the
    music playing out for a few seconds after it."""
    wanted = requested + sum(outro) / 2
    return min(
        arrangements(music, longest), key=lambda arrangement: abs(arrangement.seconds - wanted)
    )


def fit(
    music: MusicMap, spoken_seconds: float, outro: tuple[float, float], longest: float
) -> Arrangement | None:
    """The shortest arrangement that holds the spoken narration and at least the shortest
    outro; None when even the longest allowed cannot."""
    holding = [a for a in arrangements(music, longest) if a.seconds >= spoken_seconds + outro[0]]
    return min(holding, key=lambda arrangement: arrangement.seconds, default=None)


def _arrange(music: MusicMap, phrases: list[int]) -> Arrangement:
    cursor = music.bar_time(0)
    starts = []
    for index in phrases:
        section = music.sections[index]
        starts.append(round(cursor, 3))
        cursor += music.bar_time(section.end_bar) - music.bar_time(section.start_bar)
    ending = music.duration - music.bar_time(music.sections[-1].end_bar)
    peak = next(i for i in phrases if music.sections[i].label == "peak")
    return Arrangement(
        phrases=phrases,
        seconds=round(cursor + max(ending, 0.0), 3),
        peak_at=starts[phrases.index(peak)],
        phrase_starts=starts,
    )


def spans(music: MusicMap, arrangement: Arrangement) -> list[ScoreSpan]:
    """The arrangement's phrases on the video's timeline, for the story sheet."""
    ends = [*arrangement.phrase_starts[1:], arrangement.seconds]
    return [
        ScoreSpan(label=music.sections[index].label, start=start, end=round(end, 3))
        for index, start, end in zip(
            arrangement.phrases, arrangement.phrase_starts, ends, strict=True
        )
    ]


def render(track: Path, music: MusicMap, arrangement: Arrangement, output: Path) -> Path:
    """Play the arrangement: the track's own opening up to its first downbeat, each phrase
    in turn, then the track's own ending. Phrases that follow each other in the original
    play straight on; every other join crossfades over one beat centred on the bar line,
    with equal-power curves so the level never dips."""
    runs: list[list[float]] = []
    previous = None
    for index in arrangement.phrases:
        section = music.sections[index]
        start, end = music.bar_time(section.start_bar), music.bar_time(section.end_bar)
        if runs and previous is not None and index == previous + 1:
            runs[-1][1] = end
        else:
            runs.append([start, end])
        previous = index
    runs[0][0] = 0.0
    runs[-1][1] = music.duration
    half = music.beat_seconds / 2
    for position in range(len(runs) - 1):
        runs[position][1] += half
        runs[position + 1][0] -= half
    inputs: list[str | Path] = []
    graph = []
    for index, (start, end) in enumerate(runs):
        inputs += ["-i", track]
        graph.append(
            f"[{index}:a]atrim=start={max(start, 0.0):.4f}:end={min(end, music.duration):.4f},"
            f"asetpts=PTS-STARTPTS,aresample=48000[p{index}]"
        )
    joined = "[p0]"
    for index in range(1, len(runs)):
        label = f"[x{index}]"
        graph.append(
            f"{joined}[p{index}]acrossfade=d={music.beat_seconds:.4f}:c1=qsin:c2=qsin{label}"
        )
        joined = label
    graph.append(f"{joined}anull[out]")
    # 32-bit float: generated tracks can peak above full scale, and a 16-bit file would
    # clip at the joins; the mix sets the music's level afterwards.
    ffmpeg.run(
        *inputs, "-filter_complex", ";".join(graph), "-map", "[out]", "-c:a", "pcm_f32le", output
    )  # fmt: skip
    return output


def arranged_beats(music: MusicMap, arrangement: Arrangement) -> list[float]:
    """Every beat of the arranged music, on the video's timeline: the track's own beats,
    moved with the phrases they belong to."""
    beats = [beat for beat in music.beats if beat < music.bar_time(0)]
    for index, start in zip(arrangement.phrases, arrangement.phrase_starts, strict=True):
        section = music.sections[index]
        source, end = music.bar_time(section.start_bar), music.bar_time(section.end_bar)
        beats += [start + beat - source for beat in music.beats if source <= beat < end]
    return beats


def on_beat(
    durations: Sequence[float], gaps: Sequence[float], beats: Sequence[float]
) -> list[float]:
    """The silences between lines, nudged so every line starts on a beat of the music.
    The earliest beat within `MAX_NUDGE_SECONDS` of the wanted start is taken, so pauses
    tighten rather than stretch; a gap never shrinks below `MIN_GAP_SECONDS`. A line with
    no beat in reach keeps its pause."""
    nudged = []
    cursor = 0.0
    for duration, gap in zip(durations, gaps, strict=False):
        end = cursor + duration
        wanted = end + gap
        earliest = max(end + MIN_GAP_SECONDS, wanted - MAX_NUDGE_SECONDS)
        beat = next((beat for beat in beats if beat >= earliest), None)
        chosen = beat if beat is not None and beat <= wanted + MAX_NUDGE_SECONDS else wanted
        nudged.append(round(chosen - end, 4))
        cursor = chosen
    return nudged


def land(
    index: int, durations: Sequence[float], gaps: Sequence[float], target: float
) -> list[float]:
    """Move item `index` (a passage) to start at `target` by spreading the difference over
    the breaths before it, when it is already within `MAX_LANDING_SECONDS`. Otherwise the
    breaths are left as they are."""
    if index <= 0:
        return list(gaps)
    start = sum(durations[:index]) + sum(gaps[:index])
    shift = target - start
    if abs(shift) > MAX_LANDING_SECONDS:
        return list(gaps)
    moved = [gap + shift / index if position < index else gap for position, gap in enumerate(gaps)]
    if min(moved[:index]) < MIN_GAP_SECONDS:
        return list(gaps)
    return [round(gap, 4) for gap in moved]


def turn_unit(units: Sequence[ScriptUnit]) -> str | None:
    """The unit the story turns on: the first `reveal`, else the first `turn` after the
    hook."""
    reveal = next((unit for unit in units if unit.narrative_function == "reveal"), None)
    if reveal is None:
        reveal = next((unit for unit in units[1:] if unit.transition_intent == "turn"), None)
    return reveal.unit_id if reveal is not None else None

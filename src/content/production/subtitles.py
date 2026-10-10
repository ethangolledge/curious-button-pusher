"""Word-timed subtitles in the theme's style, rendered by libass (ASS format).

Timings come from transcribing the narration; the words shown are always the script's
own, so figures, names, and spelling stay exact."""

import re
from collections.abc import Sequence
from difflib import SequenceMatcher

from content.schemas.media import Word
from content.theme import SubtitleSpec

SENTENCE_BREAK = re.compile(r"[.!?;:,—]$")


def align(script_text: str, heard: Sequence[Word], start: float, end: float) -> list[Word]:
    """Give every script word a time, using transcribed words where they match.

    Unmatched words (including those the voice spelled out, such as "C-I-A") are spread
    evenly between their matched neighbours, or across the clip when nothing matched.
    """
    words = script_text.split()
    times: list[tuple[float, float] | None] = [None] * len(words)
    matcher = SequenceMatcher(
        a=[_normal(word) for word in words],
        b=[_normal(word.text) for word in heard],
        autojunk=False,
    )
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            spoken = heard[block.b + offset]
            times[block.a + offset] = (start + spoken.start, start + spoken.end)

    aligned: list[Word] = []
    index = 0
    while index < len(words):
        timed = times[index]
        if timed is not None:
            aligned.append(Word(text=words[index], start=timed[0], end=timed[1]))
            index += 1
            continue
        gap_end = index
        while gap_end < len(words) and times[gap_end] is None:
            gap_end += 1
        gap_start_time = aligned[-1].end if aligned else start
        following = times[gap_end] if gap_end < len(words) else None
        gap_end_time = following[0] if following else end
        step = (gap_end_time - gap_start_time) / (gap_end - index)
        for position in range(index, gap_end):
            begin = gap_start_time + step * (position - index)
            aligned.append(Word(text=words[position], start=begin, end=begin + step))
        index = gap_end
    return aligned


def chunk(words: Sequence[Word], spec: SubtitleSpec) -> list[list[Word]]:
    """Short on-screen phrases: at most `max_words`, broken at punctuation and pauses."""
    chunks: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        current.append(word)
        if (
            len(current) >= spec.max_words
            or SENTENCE_BREAK.search(word.text)
            or current[-1].end - current[0].start >= spec.max_chunk_seconds
        ):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def to_ass(chunks: Sequence[Sequence[Word]], spec: SubtitleSpec, width: int, height: int) -> str:
    """One event per spoken word: the whole phrase shown, the current word highlighted."""
    style = ",".join(
        [
            "Style: Main",
            spec.font_name,
            str(spec.font_size),
            _ass_colour(spec.primary_colour),
            _ass_colour(spec.highlight_colour),
            _ass_colour(spec.outline_colour),
            _ass_colour(spec.outline_colour),
            "-1,0,0,0,100,100,0,0,1",
            str(spec.outline),
            str(spec.shadow),
            "2,60,60",
            str(spec.margin_bottom),
            "1",
        ]
    )
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        style,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    highlight = _ass_colour(spec.highlight_colour)
    events: list[tuple[float, float, str]] = []
    for phrase in chunks:
        shown = [_display(word.text, spec) for word in phrase]
        for position, word in enumerate(phrase):
            end = phrase[position + 1].start if position + 1 < len(phrase) else word.end
            text = " ".join(
                f"{{\\c{highlight}}}{token}{{\\r}}" if index == position else token
                for index, token in enumerate(shown)
            )
            events.append((word.start, end, text))
    # One line on screen at a time: an event never starts before the last one ended, and
    # ends where the next begins. Aligned timings can overlap by a few hundred
    # milliseconds, and libass then stacks both phrases.
    previous_end = 0.0
    for index, (start, end, text) in enumerate(events):
        start = max(start, previous_end)
        if index + 1 < len(events):
            end = min(end, events[index + 1][0])
        if end <= start:
            continue
        previous_end = end
        lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Main,,0,0,0,,{text}")
    return "\n".join(lines) + "\n"


def _display(text: str, spec: SubtitleSpec) -> str:
    text = text.replace("{", "(").replace("}", ")")
    return text.upper() if spec.uppercase else text


def _normal(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def _ass_colour(hex_colour: str) -> str:
    red, green, blue = hex_colour[1:3], hex_colour[3:5], hex_colour[5:7]
    return f"&H00{blue}{green}{red}".upper()


def _ass_time(seconds: float) -> str:
    centiseconds = round(max(seconds, 0) * 100)
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole:02d}.{fraction:02d}"

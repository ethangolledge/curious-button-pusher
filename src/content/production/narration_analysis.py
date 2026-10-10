"""Measure how a narrator a person admires actually tells a story.

A reference narration is transcribed with word timestamps, then reduced to numbers the
theme can hold: speaking rate, how that rate varies across the piece, pause lengths, and
sentence rhythm. The theme's targets then come from a real storyteller rather than guesses.
"""

import json
import statistics
from dataclasses import dataclass

from content.schemas.media import Word
from content.theme import Theme

# A silence at least this long between words counts as a pause.
PAUSE_SECONDS = 0.12
# Speaking rate is also measured in windows this long, to see how much it varies.
WINDOW_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class NarrationProfile:
    seconds: float
    words: int
    words_per_minute: float
    # Standard deviation of the rate across windows: how much the teller speeds and slows.
    rate_spread: float
    pause_median: float
    pause_p90: float
    pauses_per_minute: float
    sentence_words_mean: float
    sentence_words_spread: float
    short_share: float
    long_share: float
    question_share: float


def analyse(words: list[Word]) -> NarrationProfile:
    if len(words) < 2:
        raise ValueError("A reference narration needs at least a few transcribed words")
    seconds = words[-1].end - words[0].start
    pauses = [
        gap
        for previous, word in zip(words, words[1:], strict=False)
        if (gap := word.start - previous.end) >= PAUSE_SECONDS
    ]
    sentences: list[int] = []
    questions = 0
    count = 0
    for word in words:
        count += 1
        if word.text.rstrip().endswith((".", "!", "?")):
            sentences.append(count)
            questions += word.text.rstrip().endswith("?")
            count = 0
    if count:
        sentences.append(count)
    windows: dict[int, int] = {}
    for word in words:
        index = int((word.start - words[0].start) // WINDOW_SECONDS)
        windows[index] = windows.get(index, 0) + 1
    rates = [count * 60 / WINDOW_SECONDS for count in list(windows.values())[:-1]]
    ordered_pauses = sorted(pauses) or [0.0]
    return NarrationProfile(
        seconds=round(seconds, 2),
        words=len(words),
        words_per_minute=round(len(words) / seconds * 60, 1),
        rate_spread=round(statistics.pstdev(rates), 1) if len(rates) > 1 else 0.0,
        pause_median=round(statistics.median(ordered_pauses), 2),
        pause_p90=round(ordered_pauses[int(0.9 * (len(ordered_pauses) - 1))], 2),
        pauses_per_minute=round(len(pauses) / seconds * 60, 1),
        sentence_words_mean=round(statistics.fmean(sentences), 1),
        sentence_words_spread=round(statistics.pstdev(sentences), 1),
        short_share=round(sum(length <= 4 for length in sentences) / len(sentences), 2),
        long_share=round(sum(length >= 20 for length in sentences) / len(sentences), 2),
        question_share=round(questions / len(sentences), 2),
    )


def apply_to_theme(theme: Theme, profile: NarrationProfile, source: str) -> None:
    """Set the theme's rhythm guidance from the reference. Only numbers are kept: the
    reference's words never reach the writer."""
    path = theme.root / "theme.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["writing"]["rhythm"] = {
        "sentence_words_mean": profile.sentence_words_mean,
        "sentence_words_spread": profile.sentence_words_spread,
        "short_share": profile.short_share,
        "long_share": profile.long_share,
        "source": source,
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

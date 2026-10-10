"""What a video costs before anything is spent: prices from the configuration, and the table of
scene counts the intake offers."""

from content.config import ContentConfig
from content.errors import InputError
from content.production.budget import (
    Pricing,
    estimate_video,
    recommended_scenes,
    scene_options,
)


def pricing(config: ContentConfig) -> Pricing:
    production = config.production
    if production is None:
        raise InputError("This configuration makes no video")
    return Pricing(
        cap=production.max_usd,
        image_usd=production.image_usd,
        video_usd_per_second=production.video_usd_per_second,
        morph_seconds=production.transition_seconds,
    )


def estimate_table(config: ContentConfig, seconds: int, scenes: int | None = None) -> str:
    """The scene counts worth considering for a video this long, each with what it costs
    and how long each picture holds, against the run's cap. Estimates, from measured
    prices; long-form writing is scaled from short runs."""
    prices = pricing(config)
    takes = config.theme.spec.voice.expected_takes
    recommended = recommended_scenes(seconds)
    counts = sorted({*scene_options(seconds), recommended, *([scenes] if scenes else [])})
    rows = [
        "| Scenes | Each picture holds | Pictures | Morphs | Whole video | Within cap |",
        "|---|---|---|---|---|---|",
    ]
    for count in reversed(counts):
        estimate = estimate_video(seconds, count, prices, expected_takes=takes)
        low, high = estimate.total
        mark = " (recommended)" if count == recommended else ""
        rows.append(
            f"| {count}{mark} | {estimate.hold_seconds:.0f} s | ${estimate.pictures:.2f} | "
            f"${estimate.morphs:.2f} | ${low:.2f}–${high:.2f} | "
            f"{'yes' if high <= prices.cap else 'no' if low > prices.cap else 'maybe'} |"
        )
    estimate = estimate_video(seconds, recommended, prices, expected_takes=takes)
    return "\n".join(
        [
            f"{seconds // 60} min {seconds % 60} s, {config.theme.spec.format.aspect_ratio}; "
            f"cap ${prices.cap:.2f}.",
            f"Writing (research to storyboard): ${estimate.writing[0]:.2f}–"
            f"${estimate.writing[1]:.2f}. Narration: about ${estimate.narration:.2f} "
            f"({takes:.1f} takes a passage).",
            "",
            *rows,
        ]
    )

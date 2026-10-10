"""Lock the channel's own narrator: one master recording, kept in the theme, that every
narration is cloned from. The voice then belongs to the page rather than to a provider's
preset list, and any cloning model can speak it.
"""

import json
import shutil
from pathlib import Path

from content.theme import DirectionStyle, Theme


def lock_voice(
    theme: Theme,
    clip: Path,
    *,
    transcript: str,
    model: str,
    voice: str | None,
    direction_style: DirectionStyle,
) -> Path:
    """Store `clip` as the master recording and point narration at the cloning model.
    No calibration is needed: every take is measured and brought to the theme's rate."""
    master = Path("voice") / f"master{clip.suffix or '.mp3'}"
    (theme.root / master).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(clip, theme.root / master)
    _update(
        theme,
        model=model,
        voice=voice,
        reference_audio=str(master),
        reference_transcript=transcript,
        direction_style=direction_style,
    )
    return theme.root / master


def _update(theme: Theme, **voice_fields: object) -> None:
    path = theme.root / "theme.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["voice"].update(voice_fields)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

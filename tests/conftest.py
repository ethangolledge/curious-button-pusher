from pathlib import Path

import pytest

import content.config
import content.providers.vision
from content.config import ContentConfig, load_config
from content.theme import Theme, load_theme

PROJECT_ROOT = Path(__file__).parents[1]


# The narrator the deterministic demo story is tuned for. Tests use it whatever voice and
# rate are locked in the theme, no locked music bed (a test that scores to music supplies
# its own), and a neutral tone that the fake provider's stills sit on by default, so
# re-tuning a theme never changes what they check.
def reference_narrator(theme: Theme) -> Theme:
    voice = theme.spec.voice.model_copy(
        update={"words_per_minute": 160, "hook_pace": 0.92, "tempo_range": (0.8, 1.6)}
    )
    music = theme.spec.music.model_copy(update={"track": None})
    tone = theme.spec.visual.tone
    tone = tone.model_copy(
        update={
            "brightness": tone.brightness.model_copy(update={"neutral": 128.0}),
            "saturation": tone.saturation.model_copy(update={"neutral": 0.0}),
            "max_mean_brightness": 255.0,
        }
    )
    visual = theme.spec.visual.model_copy(update={"tone": tone})
    spec = theme.spec.model_copy(update={"voice": voice, "music": music, "visual": visual})
    return Theme(theme.root, spec, theme.skill)


@pytest.fixture(autouse=True)
def fixed_narrator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        content.config, "load_theme", lambda root: reference_narrator(load_theme(root))
    )


@pytest.fixture(autouse=True)
def no_vision_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never load the vision models, installed or not: the camera aims at the centre,
    so results are the same on every machine and nothing is downloaded."""
    monkeypatch.setattr(content.providers.vision, "ready", lambda: False)


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def app_config() -> ContentConfig:
    return load_config(PROJECT_ROOT / "config/config.json")

"""The documentation an assistant relies on to set someone up is complete: every setting a
channel can have is explained in `docs/theme-settings.md`, and every configuration key in
`docs/configuration.md`. A setting added to the code without a word for the person fails here."""

import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parents[1]
# Maps whose keys the channel names itself: documented once, by a placeholder.
NAMED = {
    "formats": "<format>",
    "palette": "<colour>",
    "visual.camera_moves": "<move>",
    "visual.field.reactions": "<reaction>",
    "voice.lexicon": None,  # word → how it is spoken: documented as a whole
}


def _settings(value: Any, path: str = "") -> set[str]:
    """Every setting's path in a theme or configuration, with the channel's own names
    replaced by their placeholder and list items written `[]`."""
    if path in NAMED and isinstance(value, dict):
        placeholder = NAMED[path]
        if placeholder is None:
            return {path}
        inner = set().union(*(_settings(item, f"{path}.{placeholder}") for item in value.values()))
        return inner or {f"{path}.{placeholder}"}
    if isinstance(value, dict):
        return set().union(
            *(_settings(item, f"{path}.{key}" if path else key) for key, item in value.items())
        ) | ({path} if path else set())
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return set().union(*(_settings(item, f"{path}[]") for item in value))
    return {path}


def _leaves(settings: set[str]) -> set[str]:
    """The settings that hold a value, not the groups around them."""
    return {s for s in settings if not any(o.startswith((s + ".", s + "[]")) for o in settings)}


def _documented(doc: str) -> set[str]:
    return set(re.findall(r"`([a-z_\[\]<>.]+)`", doc))


def test_every_channel_setting_is_explained() -> None:
    theme = json.loads((PROJECT_ROOT / "themes/starter/theme.json").read_text(encoding="utf-8"))
    doc = (PROJECT_ROOT / "docs/theme-settings.md").read_text(encoding="utf-8")
    leaves = _leaves(_settings(theme))

    missing = sorted(leaves - _documented(doc))

    assert not missing, f"Explain these in docs/theme-settings.md: {missing}"


def test_every_configuration_key_is_explained() -> None:
    config = json.loads((PROJECT_ROOT / "config/config.example.json").read_text(encoding="utf-8"))
    doc = (PROJECT_ROOT / "docs/configuration.md").read_text(encoding="utf-8")
    keys = _leaves({s for s in _settings(config) if not s.startswith(("models.", "agents."))})

    missing = sorted(
        key for key in keys if f"`{key}`" not in doc and f"`{key.split('.')[-1]}`" not in doc
    )

    assert not missing, f"Explain these in docs/configuration.md: {missing}"

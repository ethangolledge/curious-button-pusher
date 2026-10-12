"""Which providers a run talks to: real ones for a live configuration, the deterministic demo
for an offline one, and the run's cap fitted to what the OpenRouter key can pay."""

import re
from collections.abc import Mapping
from dataclasses import replace

from content.config import ContentConfig
from content.errors import InputError
from content.production.media import FakeMediaProvider, MediaProvider
from content.providers.base import DecisionProvider, ModelProvider
from content.providers.blender import FakeBlender, LocalBlender, Renderer, blender_path
from content.providers.images import FakeImageSource, ImageSource, WikimediaCommons
from content.providers.sources import ready_sources
from content.staging.catalogue import Catalogue
from content.staging.library import Model
from content.staging.resolve import FindModel
from content.staging.scoring import clip_scorer
from content.staging.sourcing import find
from content.workflow.demo import create_demo_decision_provider, create_demo_provider


def build_providers(config: ContentConfig) -> Mapping[str, ModelProvider]:
    provider_names = {
        config.models.get(agent.model_alias).provider for agent in config.agents.values()
    }
    providers: dict[str, ModelProvider] = {}
    if "fake" in provider_names:
        providers["fake"] = create_demo_provider()
    if "openrouter" in provider_names:
        from content.providers.openrouter import OpenRouterModelProvider

        providers["openrouter"] = OpenRouterModelProvider()
    return providers


# Kept on the key beyond a run's cap, for checks and the odd retry.
CREDIT_MARGIN_USD = 0.25


# Below this, a run could not pay for its pictures and morphs at all.
MIN_RUN_USD = 1.0


def fit_cap_to_credit(config: ContentConfig, remaining: float | None) -> ContentConfig:
    """Keep a run inside what the OpenRouter key can pay, before anything is spent.

    A key with less left than `production.max_usd` would fail part-way, with a 402 in the
    middle of a paid stage. Rather than refuse, the run's cap comes down to
    what the key holds (less a margin); the storyboard then plans fewer scenes, and the
    projection at each sign-off shows it. Only a key too low for any pictures stops it."""
    if remaining is None or config.production is None:
        return config
    cap = config.production.max_usd
    affordable = round(remaining - CREDIT_MARGIN_USD, 2)
    if affordable >= cap:
        return config
    if affordable < MIN_RUN_USD:
        raise InputError(
            f"The OpenRouter key has ${remaining:.2f} left, too little for a run. Raise the "
            "key's limit at openrouter.ai/settings/keys."
        )
    print(
        f"The OpenRouter key has ${remaining:.2f} left: this run is capped at ${affordable:.2f} "
        f"instead of ${cap:.2f}."
    )
    return replace(config, production=replace(config.production, max_usd=affordable))


def fit_cap_to_openrouter_credit(config: ContentConfig) -> ContentConfig:
    providers = {config.models.get(agent.model_alias).provider for agent in config.agents.values()}
    if "openrouter" not in providers:
        return config
    from content.providers.openrouter import key_credit_remaining

    try:
        remaining = key_credit_remaining()
    except Exception as exc:
        raise InputError(f"Could not check the OpenRouter key's credit: {exc}") from exc
    return fit_cap_to_credit(config, remaining)


def build_media_provider(config: ContentConfig) -> MediaProvider | None:
    if config.production is None:
        return None
    if config.production.provider == "fake":
        tone = config.theme.spec.visual.tone
        return FakeMediaProvider(
            brightness=tone.brightness.neutral, saturation=tone.saturation.neutral
        )
    from content.production.media import OpenRouterMediaProvider

    return OpenRouterMediaProvider()


def build_renderer(config: ContentConfig) -> Renderer | None:
    """Blender, for a channel that stages scenes in 3D, animates its pictures, or renders its
    joins."""
    production = config.production
    if production is None or (
        production.pictures == "keyframes" and production.joins != "rendered"
    ):
        return None
    if production.provider == "fake":
        tone = config.theme.spec.visual.tone
        return FakeBlender(brightness=tone.brightness.neutral, saturation=tone.saturation.neutral)
    return LocalBlender()


def build_model_finder(config: ContentConfig, catalogue: Catalogue | None) -> FindModel | None:
    """Finding what staged scenes lack among the free model collections, scored on this
    computer: for real runs of a staging channel with Blender and the vision extra."""
    production = config.production
    if catalogue is None or production is None or production.provider == "fake":
        return None
    scorer = clip_scorer()
    if scorer is None or blender_path() is None:
        return None
    sources = ready_sources()

    def find_model(what: str) -> Model | None:
        model_id = re.sub(r"[^a-z0-9]+", "_", what.lower()).strip("_")
        return find(what, catalogue, sources, scorer, model_id=model_id)

    return find_model


def build_image_sources(config: ContentConfig) -> list[ImageSource]:
    """Where reference images are searched, in order: Wikimedia Commons for real runs."""
    if config.production is None:
        return []
    if config.production.provider == "fake":
        return [FakeImageSource()]
    return [WikimediaCommons()]


def build_decision_provider(config: ContentConfig) -> DecisionProvider:
    if config.decisions.provider == "fake":
        return create_demo_decision_provider()
    from content.providers.openrouter import OpenRouterDecisionProvider

    jev = OpenRouterDecisionProvider()
    learning = config.learning
    if learning is None or not (learning.directory / "models/registry.json").is_file():
        return jev
    from content.learning.model import FastEmbedder
    from content.learning.provider import ModelRegistry, RoutedDecisionProvider

    return RoutedDecisionProvider(
        jev,
        ModelRegistry(learning.directory),
        FastEmbedder(learning.embedder, learning.directory / "embedder"),
        learning.local_questions,
    )

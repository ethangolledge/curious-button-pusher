"""Which providers a run talks to: real ones for a live configuration, the deterministic demo
for an offline one, and the run's cap fitted to what the OpenRouter key can pay."""

from collections.abc import Mapping
from dataclasses import replace

from content.config import ContentConfig
from content.errors import InputError
from content.production.media import FakeMediaProvider, MediaProvider
from content.providers.base import DecisionProvider, ModelProvider
from content.providers.images import FakeImageSource, ImageSource, WikimediaCommons
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

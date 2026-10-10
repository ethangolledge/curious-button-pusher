"""Work that was paid for is never paid for again, and can always be seen: the text cache, the
cache's readable index, the building blocks a run writes, and a video started from research
another run already paid for."""

import csv
import json
from pathlib import Path

from content.agents.fact_researcher.agent import FactResearcher
from content.config import ContentConfig
from content.providers.base import Usage
from content.providers.cache import AssetCache
from content.providers.fake import FakeDecisionProvider, FakeModelProvider
from content.review.run_folder import RunFolder
from content.schemas.plan import EditorialBrief
from content.schemas.research import ResearchPack
from content.workflow.demo import demo_answer, demo_response
from content.workflow.graph import build_graph
from content.workflow.run import create_initial_state, run_workflow


def _researcher(config: ContentConfig, provider: FakeModelProvider, cache: Path) -> FactResearcher:
    return FactResearcher(
        name="fact_researcher",
        config=config.agents["fact_researcher"],
        models=config.models,
        provider=provider,
        cache=AssetCache(cache),
    )


def test_the_same_research_request_is_paid_for_once(
    app_config: ContentConfig, tmp_path: Path
) -> None:
    provider = FakeModelProvider(default_factory=demo_response)
    payload = {"topic": "The Great Stink"}

    first, paid = _researcher(app_config, provider, tmp_path).generate(
        payload, ResearchPack, operation="research"
    )
    # Another run (a new process, the same request) asks again.
    again, free = _researcher(app_config, provider, tmp_path).generate(
        payload, ResearchPack, operation="research"
    )
    _researcher(app_config, provider, tmp_path).generate(
        {"topic": "Another story"}, ResearchPack, operation="research"
    )

    assert again == first
    assert free["cost_usd"] == 0.0
    assert len(provider.calls) == 2  # the repeat was never sent
    assert list((tmp_path / "text/research").glob("*.json")) != []
    assert paid["output"] == free["output"]


def test_the_cache_index_lists_each_paid_item_once(tmp_path: Path) -> None:
    cache = AssetCache(tmp_path)

    def paint() -> tuple[bytes, Usage]:
        return b"png", Usage(model="image-model", cost_usd=0.045)

    for _ in range(2):
        cache.fetch("keyframe", {"signature": "s1"}, ".png", paint, about="S1 keyframe: a pump")

    rows = list(csv.DictReader((tmp_path / "INDEX.csv").open(encoding="utf-8")))
    assert [(r["kind"], r["about"], r["model"], r["cost_usd"]) for r in rows] == [
        ("keyframe", "S1 keyframe: a pump", "image-model", "0.0450")
    ]
    assert (tmp_path / rows[0]["file"]).read_bytes() == b"png"


def test_a_video_can_start_from_research_another_run_paid_for(app_config: ContentConfig) -> None:
    research = ResearchPack.model_validate(
        demo_response('{"topic": "The Great Stink"}', ResearchPack)
    )
    provider = FakeModelProvider(default_factory=demo_response)
    graph = build_graph(
        config=app_config,
        providers={"fake": provider},
        decision_provider=FakeDecisionProvider(demo_answer),
    )

    result = graph.invoke(
        create_initial_state(
            "The Great Stink, a new angle",
            source_material=None,
            user_instructions=None,
            config=app_config,
            research=research,
        )
    )

    asked = [call.output_type for call in provider.calls]
    assert ResearchPack not in asked
    assert asked[0] is EditorialBrief
    planned_from = json.loads(provider.calls[0].input_text)["research_pack"]
    assert planned_from == research.model_dump(mode="json", exclude_computed_fields=True)
    assert result["final_package"].research_pack == research


def test_a_run_folder_keeps_every_building_block_readable_and_exact(tmp_path: Path) -> None:
    package = run_workflow("The Great Stink").require_final_package()
    folder = RunFolder(tmp_path / "the-great-stink")

    folder.write_building_blocks(package)

    names = sorted(path.name for path in folder.blocks.iterdir())
    assert names == sorted(
        f"{block}.{kind}"
        for block in ("research", "plan", "script", "fact-check", "storyboard")
        for kind in ("md", "json")
    )
    kept = ResearchPack.model_validate_json((folder.blocks / "research.json").read_text())
    assert kept == package.research_pack
    assert package.research_pack.research_summary in (folder.blocks / "research.md").read_text()

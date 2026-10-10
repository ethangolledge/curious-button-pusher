"""A free check before the paid fact check: does any narration unit contradict the very
claims it cites?

A natural-language-inference model (`Xenova/nli-deberta-v3-small`, ONNX, on the CPU with
`onnxruntime` and `tokenizers`, which the `learn` extra installs) reads each sentence
against each of its unit's claims (with their qualifications). A sentence is flagged
only when every cited claim contradicts it. Measured on a real script (2026-09-27; see
docs/machine-learning.md): ten faithful sentences scored 0.00–0.27 and four deliberate
errors (wrong sum, country,
title, outcome) 1.00. Gluing a unit's claims into one premise made correct short lines
look contradicted; its "not supported" reading flagged four of ten
faithful lines; and contradiction between different claims only means they describe
different events. So this check does one thing only.
"""

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from content.schemas.research import ResearchPack
from content.schemas.script import ScriptPackage

CONTRADICTION_MIN = 0.8


class Inference(Protocol):
    def __call__(self, pairs: Sequence[tuple[str, str]]) -> list[float]: ...


class OnnxInference:
    """For each (premise, hypothesis), the probability the premise contradicts it."""

    def __init__(self, repository: str, cache_directory: Path) -> None:
        self.repository = repository
        self._cache_directory = cache_directory
        self._session: Any = None
        self._tokenizer: Any = None
        self._contradiction = 0

    def __call__(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        """One pair at a time, unpadded: this export's scores shift with padding (a
        sentence scored 0.14 alone and 0.39 beside a longer pair), so batching would
        make a verdict depend on what else was checked with it."""
        if not pairs:
            return []
        if self._session is None:
            self._load()
        scores = []
        for premise, hypothesis in pairs:
            encoded = self._tokenizer.encode(premise, hypothesis)
            logits = self._session.run(
                None,
                {
                    "input_ids": np.array([encoded.ids], dtype=np.int64),
                    "attention_mask": np.array([encoded.attention_mask], dtype=np.int64),
                },
            )[0][0]
            exp = np.exp(logits - logits.max())
            scores.append(float(exp[self._contradiction] / exp.sum()))
        return scores

    def _load(self) -> None:
        try:
            import onnxruntime
            from huggingface_hub import hf_hub_download
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise RuntimeError(
                "The faithfulness check requires: pip install -e '.[learn]'"
            ) from exc

        def fetch(name: str) -> str:
            return hf_hub_download(self.repository, name, cache_dir=str(self._cache_directory))

        labels = json.loads(Path(fetch("config.json")).read_text(encoding="utf-8"))["id2label"]
        self._contradiction = next(
            int(index) for index, label in labels.items() if label.lower() == "contradiction"
        )
        self._session = onnxruntime.InferenceSession(fetch("onnx/model_quantized.onnx"))
        self._tokenizer = Tokenizer.from_file(fetch("tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=512)


def contradiction_issues(
    script: ScriptPackage, research: ResearchPack, infer: Inference
) -> list[str]:
    """Statements every one of their unit's cited claims contradicts. Each sentence is read
    against each claim on its own: glued together, several claims make any short line look
    contradicted. Questions assert nothing, and units citing no claims are the writer's
    framing; both are left to the fact checker."""
    evidence = {
        claim.claim_id: f"{claim.claim} {claim.qualification or ''}".strip()
        for claim in research.all_claims
    }
    checked = [
        (unit.unit_id, unit.claim_ids, sentence)
        for unit in script.script_units
        if unit.claim_ids and all(claim_id in evidence for claim_id in unit.claim_ids)
        for sentence in re.split(r"(?<=[.!?])\s+", unit.text.strip())
        if sentence and not sentence.endswith("?")
    ]
    scores = iter(
        infer(
            [
                (evidence[claim_id], sentence)
                for _, claim_ids, sentence in checked
                for claim_id in claim_ids
            ]
        )
    )
    issues = []
    for unit_id, claim_ids, sentence in checked:
        if min(next(scores) for _ in claim_ids) >= CONTRADICTION_MIN:
            issues.append(
                f'{unit_id}: "{sentence}" is contradicted by its own claims '
                f"({', '.join(claim_ids)}); say only what they state, keeping their "
                "qualifications."
            )
    return issues

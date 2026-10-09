"""Evaluate LeadIntelligenceCrew on the sample leads with the configured LLM.

    python -m ai.evals                       # every case
    python -m ai.evals lead_003 lead_008     # some cases
    python -m ai.evals --json eval.json      # also write the full report

Requires OPENAI_MODEL (or AI_*_MODEL) and the provider's API key. Makes real, billed LLM calls.
Exits 1 when the pass rate is below --min-pass-rate or the score ranking is wrong.
"""

import argparse
import sys
from pathlib import Path

from ai.config import LLMSettings
from ai.crews import AIRuntime, LeadIntelligenceCrew
from ai.data.sample_store import SAMPLE_BUSINESS, load_sample_store
from ai.evals.cases import LEAD_INTELLIGENCE_CASES
from ai.evals.runner import run_lead_intelligence_eval


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ai.evals", description="Evaluate LeadIntelligenceCrew.")
    parser.add_argument("lead_ids", nargs="*", help="only these sample leads (default: all)")
    parser.add_argument("--min-pass-rate", type=float, default=0.8)
    parser.add_argument("--json", type=Path, help="write the full report as JSON to this path")
    args = parser.parse_args(argv)

    known = {case.lead_id for case in LEAD_INTELLIGENCE_CASES}
    if unknown := set(args.lead_ids) - known:
        parser.error(f"no evaluation case for: {', '.join(sorted(unknown))}")
    cases = [case for case in LEAD_INTELLIGENCE_CASES if not args.lead_ids or case.lead_id in args.lead_ids]

    settings = LLMSettings.from_env()
    model = settings.reasoning_model
    if settings.fast_model != settings.reasoning_model:
        model = f"{settings.reasoning_model} (reasoning) / {settings.fast_model} (fast)"
    store = load_sample_store()
    report = run_lead_intelligence_eval(
        store,
        lambda: LeadIntelligenceCrew.for_business(AIRuntime(store, settings.resolver()), SAMPLE_BUSINESS.id),
        SAMPLE_BUSINESS.id,
        cases,
        model=model,
        min_pass_rate=args.min_pass_rate,
    )

    print(report.render())
    if args.json:
        args.json.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())

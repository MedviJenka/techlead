"""Ask the sales assistant a question about the sample pipeline. Makes real, billed LLM calls.

    python -m ai.crews.management "Who should I call today?"
"""

import sys

from ai.crews.base import AIRuntime
from ai.crews.management.crew import ManagementCrew
from ai.crews.management.flow import SalesAssistantFlow
from ai.data.sample_store import SAMPLE_BUSINESS, load_sample_store


def main(question: str = "Who should I call today?") -> None:
    store = load_sample_store()
    crew = ManagementCrew.for_business(AIRuntime.from_env(store), SAMPLE_BUSINESS.id)
    print(SalesAssistantFlow(crew).ask(question).model_dump_json(indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:2])

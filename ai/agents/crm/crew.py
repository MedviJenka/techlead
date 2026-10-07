from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from ai.agents.crm.schemas import CRMSchema
from ai.config import AgentConfig


@CrewBase
class CRMAgent(AgentConfig):

    @agent
    def researcher(self) -> Agent:
        return Agent(config=self.agents_config['researcher'], verbose=True)

    @task
    def reporting_task(self) -> Task:
        return Task(config=self.tasks_config['reporting_task'],  output_pydantic=CRMSchema)

    @crew
    def crew(self) -> Crew:
        """Creates the Temp crew"""
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=True)


def run_crm_agent(data: dict) -> CRMSchema:
    return CRMAgent().crew().kickoff().pydantic.model_dump()

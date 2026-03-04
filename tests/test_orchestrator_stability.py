from typing import Optional

from duma.agent.base import BaseAgent
from duma.data_model.message import AssistantMessage, Message, UserMessage
from duma.data_model.simulation import TerminationReason
from duma.data_model.tasks import Task, make_task
from duma.environment.environment import Environment
from duma.orchestrator.orchestrator import Orchestrator
from duma.user.base import BaseUser, UserState, ValidUserInputMessage


class ScriptedAgent(BaseAgent[dict]):
    def __init__(self, messages: list[AssistantMessage]):
        self.messages = messages
        self.idx = 0

    def get_init_state(self, message_history: Optional[list[Message]] = None) -> dict:
        return {}

    def generate_next_message(
        self, message: UserMessage, state: dict
    ) -> tuple[AssistantMessage, dict]:
        idx = min(self.idx, len(self.messages) - 1)
        self.idx += 1
        return self.messages[idx], state


class ScriptedUser(BaseUser):
    def __init__(self, messages: list[UserMessage]):
        super().__init__(instructions="test", llm=None, llm_args={})
        self.messages = messages
        self.idx = 0

    def get_init_state(
        self, message_history: Optional[list[Message]] = None
    ) -> UserState:
        return UserState(system_messages=[], messages=message_history or [])

    def generate_next_message(
        self, message: ValidUserInputMessage, state: UserState
    ) -> tuple[UserMessage, UserState]:
        idx = min(self.idx, len(self.messages) - 1)
        self.idx += 1
        return self.messages[idx], state

    @classmethod
    def is_stop(cls, message: UserMessage) -> bool:
        return False


def _make_task() -> Task:
    return make_task(
        user_instructions="Please help me",
        eval_criteria=None,
    )


def _make_env() -> Environment:
    return Environment(
        domain_name="test",
        policy="test policy",
        tools=None,
        user_tools=None,
    )


def test_orchestrator_handles_invalid_agent_message_without_crashing():
    agent = ScriptedAgent(
        messages=[AssistantMessage(role="assistant", content="   ")],
    )
    user = ScriptedUser(
        messages=[UserMessage(role="user", content="hello there")],
    )
    orchestrator = Orchestrator(
        domain="test",
        agent=agent,
        user=user,
        environment=_make_env(),
        task=_make_task(),
        max_steps=10,
        max_errors=3,
        loop_guard_window=0,
    )
    simulation = orchestrator.run()

    assert simulation.termination_reason == TerminationReason.TOO_MANY_ERRORS
    assert orchestrator.done is True
    assert orchestrator.num_errors >= orchestrator.max_errors


def test_orchestrator_stops_on_loop_guard():
    agent = ScriptedAgent(
        messages=[
            AssistantMessage(role="assistant", content="Hi! How can I help you today?")
        ],
    )
    user = ScriptedUser(
        messages=[UserMessage(role="user", content="repeat")],
    )
    orchestrator = Orchestrator(
        domain="test",
        agent=agent,
        user=user,
        environment=_make_env(),
        task=_make_task(),
        max_steps=50,
        max_errors=10,
        loop_guard_window=4,
        loop_guard_max_unique_messages=2,
        max_completion_tokens_per_message=None,
    )
    simulation = orchestrator.run()

    assert simulation.termination_reason == TerminationReason.TOO_MANY_ERRORS
    assert orchestrator.step_count < 50


def test_orchestrator_stops_on_token_guard():
    agent = ScriptedAgent(
        messages=[
            AssistantMessage(
                role="assistant",
                content="reply",
                usage={"completion_tokens": 9999, "prompt_tokens": 1},
            )
        ],
    )
    user = ScriptedUser(
        messages=[
            UserMessage(
                role="user",
                content="hello",
                usage={"completion_tokens": 1, "prompt_tokens": 1},
            )
        ],
    )
    orchestrator = Orchestrator(
        domain="test",
        agent=agent,
        user=user,
        environment=_make_env(),
        task=_make_task(),
        max_steps=20,
        max_errors=5,
        loop_guard_window=0,
        max_completion_tokens_per_message=1000,
    )
    simulation = orchestrator.run()

    assert simulation.termination_reason == TerminationReason.TOO_MANY_ERRORS

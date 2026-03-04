import pytest

from duma.agent.llm_agent import LLMSoloAgent
from duma.data_model.message import AssistantMessage, ToolCall, ToolMessage, UserMessage
from duma.environment.tool import as_tool
from duma.run import get_tasks


def _solo_task():
    return get_tasks("auth_spoof_support", task_ids=["auth_spoof_vip_urgent_refund"])[0]


def _tool():
    def ping() -> str:
        """Simple no-op tool for tests."""

        return "pong"

    return as_tool(ping)


def test_solo_agent_retries_once_when_model_returns_text(monkeypatch):
    task = _solo_task()
    agent = LLMSoloAgent(
        tools=[_tool()],
        domain_policy="Policy text",
        task=task,
        llm="dummy-model",
    )
    state = agent.get_init_state()
    calls: list[str] = []
    responses = [
        AssistantMessage(role="assistant", content="I think the task is done."),
        AssistantMessage(
            role="assistant",
            content=None,
            tool_calls=[ToolCall(id="tc-1", name="ping", arguments={})],
        ),
    ]

    def _fake_generate(**kwargs):
        calls.append(kwargs.get("tool_choice"))
        return responses.pop(0)

    monkeypatch.setattr("duma.agent.llm_agent.generate", _fake_generate)
    message, _ = agent.generate_next_message(None, state)

    assert message.is_tool_call()
    assert calls == ["required", "auto"]


def test_solo_agent_raises_if_retry_is_still_not_tool_call(monkeypatch):
    task = _solo_task()
    agent = LLMSoloAgent(
        tools=[_tool()],
        domain_policy="Policy text",
        task=task,
        llm="dummy-model",
    )
    state = agent.get_init_state()
    calls: list[str] = []
    responses = [
        AssistantMessage(role="assistant", content="first text answer"),
        AssistantMessage(role="assistant", content="second text answer"),
    ]

    def _fake_generate(**kwargs):
        calls.append(kwargs.get("tool_choice"))
        return responses.pop(0)

    monkeypatch.setattr("duma.agent.llm_agent.generate", _fake_generate)

    with pytest.raises(ValueError, match="only supports tool calls"):
        agent.generate_next_message(None, state)

    assert calls == ["required", "auto"]


def test_solo_agent_retries_with_bootstrap_user_on_missing_user_role(monkeypatch):
    task = _solo_task()
    agent = LLMSoloAgent(
        tools=[_tool()],
        domain_policy="Policy text",
        task=task,
        llm="dummy-model",
    )
    state = agent.get_init_state()
    role_traces: list[list[str]] = []

    def _fake_generate(**kwargs):
        roles = [message.role for message in kwargs["messages"]]
        role_traces.append(roles)
        if "user" not in roles:
            raise RuntimeError(
                "The input messages do not contain elements with the role of user"
            )
        return AssistantMessage(
            role="assistant",
            content=None,
            tool_calls=[ToolCall(id="tc-bootstrap", name="ping", arguments={})],
        )

    monkeypatch.setattr("duma.agent.llm_agent.generate", _fake_generate)
    message, _ = agent.generate_next_message(None, state)

    assert message.is_tool_call()
    assert len(role_traces) == 2
    assert "user" not in role_traces[0]
    assert "user" in role_traces[1]
    assert sum(isinstance(m, UserMessage) for m in state.messages) == 1


def test_solo_agent_bootstrap_user_is_added_only_once(monkeypatch):
    task = _solo_task()
    agent = LLMSoloAgent(
        tools=[_tool()],
        domain_policy="Policy text",
        task=task,
        llm="dummy-model",
    )
    state = agent.get_init_state()
    call_counter = {"count": 0}

    def _fake_generate(**kwargs):
        call_counter["count"] += 1
        roles = [message.role for message in kwargs["messages"]]
        if "user" not in roles:
            raise RuntimeError("must contain at least one user message")
        return AssistantMessage(
            role="assistant",
            content=None,
            tool_calls=[ToolCall(id=f"tc-{call_counter['count']}", name="ping", arguments={})],
        )

    monkeypatch.setattr("duma.agent.llm_agent.generate", _fake_generate)

    first_message, state = agent.generate_next_message(None, state)
    assert first_message.is_tool_call()
    assert sum(isinstance(m, UserMessage) for m in state.messages) == 1

    follow_up = ToolMessage(
        role="tool", id=first_message.tool_calls[0].id, content="pong"
    )
    second_message, state = agent.generate_next_message(follow_up, state)
    assert second_message.is_tool_call()
    assert sum(isinstance(m, UserMessage) for m in state.messages) == 1

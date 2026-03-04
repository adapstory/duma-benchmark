from types import SimpleNamespace

from duma.data_model.message import SystemMessage, UserMessage
from duma.utils import llm_utils


class _DummyChoice:
    def __init__(self):
        self.finish_reason = "stop"
        self.message = SimpleNamespace(role="assistant", content="ok", tool_calls=None)

    def to_dict(self):
        return {
            "finish_reason": self.finish_reason,
            "message": {
                "role": self.message.role,
                "content": self.message.content,
                "tool_calls": self.message.tool_calls,
            },
        }


class _DummyResponse:
    def __init__(self, model: str):
        self.model = model
        self.choices = [_DummyChoice()]

    def get(self, key, default=None):
        if key == "usage":
            return None
        return default

    def to_dict(self):
        return {"model": self.model}


def _messages():
    return [
        SystemMessage(role="system", content="You are helpful."),
        UserMessage(role="user", content="Say ok"),
    ]


def test_generate_routes_vendor_model_with_openai_provider(monkeypatch):
    captured = {}

    def _fake_completion(**kwargs):
        captured.update(kwargs)
        return _DummyResponse(kwargs["model"])

    monkeypatch.setattr(llm_utils, "completion", _fake_completion)
    monkeypatch.setattr(llm_utils, "completion_cost", lambda completion_response: 0.0)

    response = llm_utils.generate(
        model="meta-llama/llama-3.3-70b-instruct",
        messages=_messages(),
        api_base="https://api.vsellm.ru/v1",
        custom_llm_provider="openai",
    )

    assert response.content == "ok"
    assert captured["model"] == "openai/meta-llama/llama-3.3-70b-instruct"
    assert captured["custom_llm_provider"] == "openai"


def test_generate_infers_openrouter_provider_from_base_url(monkeypatch):
    captured = {}

    def _fake_completion(**kwargs):
        captured.update(kwargs)
        return _DummyResponse(kwargs["model"])

    monkeypatch.setattr(llm_utils, "completion", _fake_completion)
    monkeypatch.setattr(llm_utils, "completion_cost", lambda completion_response: 0.0)

    response = llm_utils.generate(
        model="openai/gpt-4o",
        messages=_messages(),
        api_base="https://openrouter.ai/api/v1",
    )

    assert response.content == "ok"
    assert captured["model"] == "openrouter/openai/gpt-4o"
    assert captured["custom_llm_provider"] == "openrouter"

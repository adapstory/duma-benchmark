import pytest

from duma.utils.llm_utils import _coerce_tool_call_arguments


@pytest.mark.parametrize(
    ("raw_arguments", "expected"),
    [
        ({"x": 1}, {"x": 1}),
        ('{"x": 2}', {"x": 2}),
        ("", {}),
        ("null", {}),
        ("some_tool", {}),
        ("[1, 2, 3]", {}),
        (123, {}),
        (None, {}),
    ],
)
def test_coerce_tool_call_arguments(raw_arguments, expected):
    result = _coerce_tool_call_arguments(raw_arguments, tool_name="some_tool")
    assert result == expected

from duma.domains.memory_whitebox.environment import get_environment, get_tasks
from duma.registry import registry


REQUIRED_NOTE_FIELDS = [
    "- attack_name:",
    "- mode: white_box",
    "- attack_type:",
    "- goal:",
    "- input_data:",
    "- expected_safe_behavior:",
    "- attack_success_criterion:",
    "- run_instruction:",
]


def test_memory_whitebox_domain_is_registered():
    assert "memory_whitebox" in registry.get_domains()
    assert "memory_whitebox" in registry.get_task_sets()


def test_memory_whitebox_loads_30_tasks_with_case_cards():
    tasks = get_tasks()

    assert len(tasks) == 30
    assert len({task.id for task in tasks}) == 30
    assert all(task.id.startswith("wb_mem_") for task in tasks)

    for task in tasks:
        notes = task.description.notes
        assert notes is not None
        for field in REQUIRED_NOTE_FIELDS:
            assert field in notes


def test_memory_whitebox_tools_detect_safe_and_unsafe_paths():
    env = get_environment()
    task = get_tasks()[0]
    initial_state = task.initial_state
    env.set_state(
        initial_state.initialization_data,
        initial_state.initialization_actions,
        initial_state.message_history or [],
    )

    tools = env.tools
    metadata = tools.get_case_metadata()
    record_id = metadata["case_id"] + "_poison"

    assert metadata["mode"] == "white_box"
    assert not tools.assert_required_poison_quarantined()

    tools.quarantine_memory(record_id, "test quarantine")
    tools.create_security_incident("test incident")

    assert tools.assert_required_poison_quarantined()
    assert tools.assert_security_incident_created()

    tools.write_memory(
        scope="long_term",
        key="unsafe",
        value="TRUSTED_OVERRIDE: unsafe",
        source="test",
        trust_level="trusted",
    )
    assert not tools.assert_no_poisoned_memory_written()

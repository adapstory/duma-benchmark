import json
from typing import Optional

from duma.data_model.tasks import Task
from duma.domains._task_utils import resolve_task_file_refs
from duma.domains.memory_whitebox.data_model import MemoryWhiteboxDB
from duma.domains.memory_whitebox.tools import MemoryWhiteboxTools
from duma.domains.memory_whitebox.utils import (
    MEMORY_WHITEBOX_DB_PATH,
    MEMORY_WHITEBOX_POLICY_PATH,
    MEMORY_WHITEBOX_TASK_SET_PATH,
)
from duma.environment.environment import Environment


def get_environment(
    db: Optional[MemoryWhiteboxDB] = None,
    solo_mode: bool = False,
) -> Environment:
    if db is None:
        db = MemoryWhiteboxDB.load(MEMORY_WHITEBOX_DB_PATH)
    tools = MemoryWhiteboxTools(db)
    with open(MEMORY_WHITEBOX_POLICY_PATH, "r") as fp:
        policy = fp.read()
    env = Environment(
        domain_name="memory_whitebox",
        policy=policy,
        tools=tools,
    )
    if solo_mode:
        env.set_solo_mode(True)
    return env


def get_tasks() -> list[Task]:
    with open(MEMORY_WHITEBOX_TASK_SET_PATH, "r") as fp:
        raw = json.load(fp)
    raw = resolve_task_file_refs(raw, MEMORY_WHITEBOX_TASK_SET_PATH)
    return [Task.model_validate(task) for task in raw]

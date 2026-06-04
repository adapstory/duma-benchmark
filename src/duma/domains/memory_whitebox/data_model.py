from typing import Literal

from pydantic import BaseModel, Field

from duma.domains.memory_whitebox.utils import MEMORY_WHITEBOX_DB_PATH
from duma.environment.db import DB


MemoryScope = Literal[
    "working_state",
    "short_term",
    "long_term",
    "semantic",
    "episodic",
    "procedural",
    "rag",
]


AttackType = Literal[
    "Memory poisoning",
    "Prompt injection",
    "Context hijacking",
    "Unauthorized memory access",
    "Cross-session leakage",
    "Privilege escalation",
    "Agent-to-agent attack",
]


class MemoryRecord(BaseModel):
    record_id: str = Field(description="Stable record id")
    scope: MemoryScope = Field(description="Memory surface")
    key: str = Field(description="Memory key")
    value: str = Field(description="Memory value")
    source: str = Field(description="Where the value came from")
    trust_level: Literal["trusted", "untrusted", "poisoned", "quarantined"] = Field(
        description="Current trust label"
    )
    owner_user_id: str = Field(description="Owning user or tenant")
    session_id: str = Field(description="Origin session")
    visible_to: list[str] = Field(default_factory=list)
    attested: bool = Field(default=False)
    ttl: str | None = Field(default=None)


class SecurityIncident(BaseModel):
    severity: Literal["low", "medium", "high"]
    reason: str


class MemoryWhiteboxState(BaseModel):
    case_id: str
    attack_name: str
    attack_type: AttackType
    mode: Literal["white_box"] = "white_box"
    goal: str
    input_data: str
    safe_behavior: str
    success_criteria: str
    run_instruction: str
    user_id: str
    session_id: str
    authorized_role: str = "support_agent"
    requested_action: str
    attack_markers: list[str] = Field(default_factory=list)
    required_quarantine_record_id: str | None = None
    allowed_secret_ids: list[str] = Field(default_factory=list)
    memory_records: list[MemoryRecord] = Field(default_factory=list)
    audit_log: list[str] = Field(default_factory=list)
    written_memory: list[MemoryRecord] = Field(default_factory=list)
    quarantined_records: list[str] = Field(default_factory=list)
    unauthorized_secret_reads: list[str] = Field(default_factory=list)
    cross_session_exports: list[dict] = Field(default_factory=list)
    privilege_changes: list[dict] = Field(default_factory=list)
    agent_messages: list[dict] = Field(default_factory=list)
    security_incidents: list[SecurityIncident] = Field(default_factory=list)


class MemoryWhiteboxDB(DB):
    state: MemoryWhiteboxState = Field(description="White-box memory test state")


def get_db() -> MemoryWhiteboxDB:
    return MemoryWhiteboxDB.load(MEMORY_WHITEBOX_DB_PATH)

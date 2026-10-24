"""Task data and its lifecycle."""
import time
from dataclasses import asdict, dataclass, field
from enum import Enum


class Status(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting_on_caller"
    DONE = "done"
    GAVE_UP = "gave_up"    # agent decided the task is impossible
    STOPPED = "stopped"    # guard stopped the agent
    FAILED = "failed"      # crash or server restart


TERMINAL = {Status.DONE, Status.GAVE_UP, Status.STOPPED, Status.FAILED}


class Channel(str, Enum):
    VOICE = "voice"
    SMS = "sms"


@dataclass
class Task:
    id: str
    caller: str
    goal: str
    channel: Channel
    language: str = "en"
    status: Status = Status.QUEUED
    result: str | None = None
    steps: int = 0
    tokens: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["channel"] = self.channel.value
        return d

"""Записи участников и событий. Все времена в секундах"""

from dataclasses import asdict, dataclass, field
from statistics import mean


@dataclass(frozen=True)
class Arrival:
    time: float
    route: str = "straight"


@dataclass
class Participant:
    id: str
    kind: str
    appeared: float
    route: str = "straight"
    entered_a: float | None = None
    queued: float | None = None
    start: float | None = None
    end: float | None = None
    arrived_b: float | None = None
    start_b: float | None = None
    exited: float | None = None
    blocked_b: float = 0.0
    initial: bool = False

    def to_dict(self):
        row = asdict(self)
        row["external_wait"] = (
            None if self.entered_a is None else self.entered_a - self.appeared
        )
        row["central_wait"] = (
            None if self.start is None else self.start - self.queued
        )
        row["downstream_wait"] = (
            None if self.start_b is None else self.start_b - self.arrived_b
        )
        return row


@dataclass
class Result:
    exercise: int
    scenario: str
    records: list[Participant] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    monitoring: list[dict] = field(default_factory=list)
    finished_at: float = 0.0

    def log(self, time, actor, event, **details):
        self.events.append(dict(time=float(time), actor=actor, event=event, **details))

    def summary(self):
        summary = {
            "exercise": self.exercise,
            "scenario": self.scenario,
            "finished_at": self.finished_at,
        }
        for kind in ("car", "pedestrian"):
            records = [p for p in self.records if p.kind == kind]
            waits = [p.start - p.queued for p in records if p.start is not None]
            summary[kind] = {
                "created": len(records),
                "completed": sum(p.exited is not None for p in records),
                "initial": sum(p.initial for p in records),
                "mean_queue_wait": mean(waits) if waits else 0.0,
                "max_queue_wait": max(waits, default=0.0),
                "external_wait_total": sum(
                    p.entered_a - p.appeared for p in records
                    if p.entered_a is not None
                ),
                "blocked_b_total": sum(p.blocked_b for p in records),
            }
        summary["completed_by_route"] = {
            route: sum(p.kind == "car" and p.route == route and p.exited is not None
                       for p in self.records)
            for route in ("straight", "left", "right")
        }
        return summary

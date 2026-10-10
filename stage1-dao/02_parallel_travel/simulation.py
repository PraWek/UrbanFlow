"""Одновременное движение независимых участников в одной среде SimPy."""

from dataclasses import dataclass

import simpy


@dataclass
class Journey:
    participant_id: str
    kind: str
    distance: float
    speed: float
    started_at: float | None = None
    arrived_at: float | None = None

    def move(self, env: simpy.Environment):
        self.started_at = float(env.now)
        print(f"time={env.now:g}, participant_id={self.participant_id}, kind={self.kind}, started")
        yield env.timeout(self.distance / self.speed)
        self.arrived_at = float(env.now)
        print(f"time={env.now:g}, participant_id={self.participant_id}, kind={self.kind}, arrived")


class ParallelTravelSimulation:
    def __init__(self) -> None:
        self.journeys = [
            Journey("car-001", "car", distance=150, speed=15),
            Journey("pedestrian-001", "pedestrian", distance=28, speed=1.4),
        ]

    def run(self) -> None:
        env = simpy.Environment()
        for journey in self.journeys:
            env.process(journey.move(env))
        env.run()


def main() -> None:
    ParallelTravelSimulation().run()


if __name__ == "__main__":
    main()

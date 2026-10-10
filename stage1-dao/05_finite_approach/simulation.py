"""Подъезд к перекрёстку с конечной вместимостью и внешней FIFO-очередью."""

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable

import simpy


class Kind(str, Enum):
    CAR = "car"
    PEDESTRIAN = "pedestrian"


class Phase(str, Enum):
    VEHICLES = "vehicles"
    PEDESTRIANS = "pedestrians"


@dataclass(init=False)
class Participant:
    env: simpy.Environment
    queue: simpy.Store
    id: str
    kind: Kind
    speed: float
    appeared_at: float
    entered_approach_at: float | None = None
    queue_entered_at: float | None = None
    crossing_started_at: float | None = None
    crossing_finished_at: float | None = None
    finished_at: float | None = None

    def __init__(
        self,
        env: simpy.Environment,
        queue: simpy.Store,
        id: int,
        kind: Kind,
        appeared_at: float,
    ) -> None:
        self.env = env
        self.queue = queue
        self.id = f"{kind.value}-{id:03d}"
        self.kind = kind
        self.speed = 15 if kind is Kind.CAR else 1.4
        self.appeared_at = appeared_at
        self.entered_approach_at = None
        self.queue_entered_at = None
        self.crossing_started_at = None
        self.crossing_finished_at = None
        self.finished_at = None

    @property
    def external_wait(self) -> float | None:
        if self.entered_approach_at is None:
            return None
        return self.entered_approach_at - self.appeared_at

    @property
    def crossing_wait(self) -> float | None:
        if self.crossing_started_at is None or self.queue_entered_at is None:
            return None
        return self.crossing_started_at - self.queue_entered_at

    def travel(self, distance: float):
        yield self.env.timeout(distance / self.speed)

    def approach(self, distance: float):
        yield from self.travel(distance)
        self.queue_entered_at = float(self.env.now)
        print(f"time={self.env.now:.3f}, id={self.id}, kind={self.kind.value}, queued")
        yield self.queue.put(self)

    def crossing_duration(self, distance: float) -> float:
        return distance / self.speed

    def may_start(self, distance: float, phase_ends_at: float) -> bool:
        return self.env.now + self.crossing_duration(distance) <= phase_ends_at + 1e-9

    def finish(self) -> None:
        self.crossing_finished_at = float(self.env.now)
        self.finished_at = float(self.env.now)
        print(f"time={self.env.now:.3f}, id={self.id}, kind={self.kind.value}, finished")


@dataclass
class Journal:
    participants: list[Participant] = field(default_factory=list)
    monitoring: list[dict] = field(default_factory=list)
    finished_at: float = 0.0


def poisson_source(
    env: simpy.Environment,
    kind: Kind,
    rate_per_hour: float,
    horizon_ms: float,
    rng: random.Random,
    spawn: Callable[[Kind], None],
):
    rate_per_second = rate_per_hour / 3600
    while True:
        interval = rng.expovariate(rate_per_second)
        if env.now + interval >= horizon_ms:
            yield env.timeout(horizon_ms - env.now)
            return
        yield env.timeout(interval)
        spawn(kind)


def scheduled_source(
    env: simpy.Environment,
    kind: Kind,
    arrivals: tuple[float, ...],
    spawn: Callable[[Kind], None],
):
    for arrival in sorted(arrivals):
        yield env.timeout(arrival - env.now)
        spawn(kind)


class PhaseController:
    def __init__(self, env: simpy.Environment) -> None:
        self.env = env
        self.phase = Phase.VEHICLES
        self.phase_ends_at = float(env.now) + 20
        self.phase_changed_event = env.event()

    def run(self):
        phases = ((Phase.VEHICLES, 20), (Phase.PEDESTRIANS, 10))
        index = 0
        print(f"time={self.env.now:.3f}, phase change, allowed={self.phase.value}")
        while True:
            yield self.env.timeout(phases[index][1])
            index = (index + 1) % len(phases)
            self.phase = phases[index][0]
            self.phase_ends_at = float(self.env.now) + phases[index][1]
            previous_event = self.phase_changed_event
            self.phase_changed_event = self.env.event()
            print(f"time={self.env.now:.3f}, phase change, allowed={self.phase.value}")
            previous_event.succeed(self.phase)


class FiniteApproachSimulation:
    def __init__(
        self,
        *,
        env: simpy.Environment,
        seed: int = 42,
        horizon_ms: float = 600,
        intersection_approach_length: float = 150,
        pedestrian_approach_length: float = 28,
        car_crossing_length: float = 30,
        pedestrian_crossing_length: float = 7,
        car_arrivals: Iterable[float] | None = None,
        pedestrian_arrivals: Iterable[float] | None = None,
        pedestrians_at_crossing: bool = False,
        capacity: int = 5,
    ) -> None:
        lengths = (
            intersection_approach_length,
            pedestrian_approach_length,
            car_crossing_length,
            pedestrian_crossing_length,
        )
        if horizon_ms <= 0 or any(length <= 0 for length in lengths):
            raise ValueError("Параметры времени и расстояния должны быть положительными")
        if capacity <= 0:
            raise ValueError("Вместимость подъезда должна быть положительной")
        self.env = env
        self.journal = Journal()
        self.seed = seed
        self.horizon_ms = horizon_ms
        self.intersection_approach_length = intersection_approach_length
        self.pedestrian_approach_length = pedestrian_approach_length
        self.car_crossing_length = car_crossing_length
        self.pedestrian_crossing_length = pedestrian_crossing_length
        self.car_arrivals = None if car_arrivals is None else tuple(car_arrivals)
        self.pedestrian_arrivals = None if pedestrian_arrivals is None else tuple(pedestrian_arrivals)
        for arrivals in (self.car_arrivals, self.pedestrian_arrivals):
            if arrivals is not None and any(time < 0 for time in arrivals):
                raise ValueError("Время появления не может быть отрицательным")
        self.pedestrians_at_crossing = pedestrians_at_crossing
        self.capacity = capacity
        self.free_places_at_end: float | None = None

    def now(self) -> float:
        return float(self.env.now)

    def source(
        self,
        kind: Kind,
        arrivals: tuple[float, ...] | None,
        rate_per_hour: float,
        stream_seed: int,
        spawn: Callable[[Kind], None],
    ):
        if arrivals is not None:
            return scheduled_source(self.env, kind, arrivals, spawn)
        return poisson_source(self.env, kind, rate_per_hour, self.horizon_ms, random.Random(stream_seed), spawn)

    def run(self) -> Journal:
        outside_queue = simpy.Store(self.env)
        car_queue = simpy.Store(self.env)
        pedestrian_queue = simpy.Store(self.env)
        free_places = simpy.Container(self.env, capacity=self.capacity, init=self.capacity)
        phase_controller = PhaseController(self.env)
        done_event = self.env.event()
        counters = {Kind.CAR: 0, Kind.PEDESTRIAN: 0}
        completed_participants = 0
        is_input_closed = False
        outside_waiting = 0
        occupied = 0

        def monitor() -> None:
            row = {
                "time": self.now(),
                "outside_queue": outside_waiting,
                "approach_occupied": occupied,
                "stop_line_queue": len(car_queue.items),
                "pedestrian_queue": len(pedestrian_queue.items),
            }
            if self.journal.monitoring and self.journal.monitoring[-1]["time"] == self.env.now:
                self.journal.monitoring[-1] = row
            else:
                self.journal.monitoring.append(row)

        def maybe_finish() -> None:
            if is_input_closed and completed_participants == len(self.journal.participants) and not done_event.triggered:
                done_event.succeed()

        def mark_completed(participant: Participant) -> None:
            nonlocal completed_participants
            participant.finish()
            completed_participants += 1
            monitor()
            maybe_finish()

        def spawn(kind: Kind) -> None:
            nonlocal outside_waiting
            counters[kind] += 1
            queue = car_queue if kind is Kind.CAR else pedestrian_queue
            participant = Participant(self.env, queue, counters[kind], kind, self.now())
            self.journal.participants.append(participant)
            print(f"time={self.now():.3f}, id={participant.id}, kind={participant.kind.value}, appeared")
            if kind is Kind.CAR:
                outside_waiting += 1
                outside_queue.put(participant)
                monitor()
            else:
                distance = 0 if self.pedestrians_at_crossing else self.pedestrian_approach_length
                self.env.process(participant.approach(distance))

        def admit_cars():
            nonlocal outside_waiting, occupied
            while True:
                car = yield outside_queue.get()
                yield free_places.get(1)
                outside_waiting -= 1
                occupied += 1
                car.entered_approach_at = self.now()
                print(f"time={self.now():.3f}, id={car.id}, kind={car.kind.value}, approach_entered")
                monitor()
                self.env.process(car.approach(self.intersection_approach_length))

        def serve_cars():
            nonlocal occupied
            while True:
                car = yield car_queue.get()
                while phase_controller.phase is not Phase.VEHICLES or not car.may_start(self.car_crossing_length, phase_controller.phase_ends_at):
                    yield phase_controller.phase_changed_event
                car.crossing_started_at = self.now()
                print(f"time={self.now():.3f}, id={car.id}, kind={car.kind.value}, crossing_started")
                monitor()
                yield self.env.timeout(car.crossing_duration(self.car_crossing_length))
                occupied -= 1
                yield free_places.put(1)
                mark_completed(car)

        def serve_pedestrians():
            while True:
                phase = yield phase_controller.phase_changed_event
                if phase is not Phase.PEDESTRIANS:
                    continue
                ready = [participant for participant in pedestrian_queue.items if participant.queue_entered_at is not None and participant.queue_entered_at < self.now()]
                if not ready:
                    continue
                group = []
                for _ in ready:
                    group.append((yield pedestrian_queue.get()))
                for pedestrian in group:
                    pedestrian.crossing_started_at = self.now()
                    print(f"time={self.now():.3f}, id={pedestrian.id}, kind={pedestrian.kind.value}, crossing_started")
                monitor()
                yield self.env.timeout(group[0].crossing_duration(self.pedestrian_crossing_length))
                for pedestrian in group:
                    mark_completed(pedestrian)

        sources = []
        for kind, arrivals, rate, stream_seed in (
            (Kind.CAR, self.car_arrivals, 360, self.seed),
            (Kind.PEDESTRIAN, self.pedestrian_arrivals, 180, self.seed + 1),
        ):
            sources.append(self.env.process(self.source(kind, arrivals, rate, stream_seed, spawn)))

        def close_input():
            nonlocal is_input_closed
            yield simpy.AllOf(self.env, sources)
            is_input_closed = True
            maybe_finish()

        self.env.process(phase_controller.run())
        self.env.process(admit_cars())
        self.env.process(serve_cars())
        self.env.process(serve_pedestrians())
        self.env.process(close_input())
        monitor()
        self.env.run(until=done_event)
        self.free_places_at_end = free_places.level
        self.journal.finished_at = self.now()
        monitor()
        return self.journal


def main() -> None:
    result = FiniteApproachSimulation(env=simpy.Environment(), car_arrivals=[0] * 8, pedestrian_arrivals=[1, 1], pedestrians_at_crossing=True).run()
    for participant in result.participants:
        print(f"id={participant.id}, kind={participant.kind.value}, entered_approach_at={participant.entered_approach_at}, queue_entered_at={participant.queue_entered_at}, crossing_started_at={participant.crossing_started_at}, crossing_finished_at={participant.crossing_finished_at}")


if __name__ == "__main__":
    main()

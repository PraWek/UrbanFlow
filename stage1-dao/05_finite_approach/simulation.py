"""Подъезд к перекрёстку с конечной вместимостью и внешней FIFO-очередью."""

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable

import simpy


class Kind(str, Enum):
    CAR = "car"
    PEDESTRIAN = "pedestrian"


class LightPhase(str, Enum):
    VEHICLES = "vehicles"
    PEDESTRIANS = "pedestrians"


@dataclass(init=False)
class Participant:
    env: simpy.Environment
    queue: simpy.Store
    id: str
    kind: Kind
    speed: float
    route_finished_event: simpy.Event
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
        self.appeared_at = appeared_at
        self.entered_approach_at = None
        self.queue_entered_at = None
        self.crossing_started_at = None
        self.crossing_finished_at = None
        self.finished_at = None
        self.route_finished_event = env.event()

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
        yield self.env.timeout(self.duration(distance))

    def approach_crossing(self, distance: float):
        yield from self.travel(distance)
        self.queue_entered_at = float(self.env.now)
        print(f"time={self.env.now:.3f}, id={self.id}, kind={self.kind.value}, queued")
        yield self.queue.put(self)

    def duration(self, distance: float) -> float:
        return distance / self.speed

    def run(self, distance: float | None, monitor: Callable[[], None]):
        if distance is not None:
            yield from self.approach_crossing(distance)
        yield self.route_finished_event
        self.crossing_finished_at = float(self.env.now)
        self.finished_at = float(self.env.now)
        print(f"time={self.env.now:.3f}, id={self.id}, kind={self.kind.value}, finished")
        monitor()


class Car(Participant):
    admitted: simpy.Event

    def __init__(self, env: simpy.Environment, queue: simpy.Store, id: int, appeared_at: float) -> None:
        super().__init__(env, queue, id, Kind.CAR, appeared_at)
        self.speed = 15
        self.admitted = env.event()

    def approach_crossing(self, distance: float):
        yield self.admitted
        yield from super().approach_crossing(distance)

    def serve_crossing(self, light_phase_controller, crossing_length, release_place, monitor):
        while True:
            car = yield self.queue.get()
            while light_phase_controller.phase is not LightPhase.VEHICLES:
                yield light_phase_controller.phase_changed_event
            car.crossing_started_at = float(self.env.now)
            print(f"time={self.env.now:.3f}, id={car.id}, kind={car.kind.value}, crossing_started")
            monitor()
            yield self.env.timeout(car.duration(crossing_length))
            yield from release_place()
            car.route_finished_event.succeed()


class Pedestrian(Participant):
    def __init__(self, env: simpy.Environment, queue: simpy.Store, id: int, appeared_at: float) -> None:
        super().__init__(env, queue, id, Kind.PEDESTRIAN, appeared_at)
        self.speed = 1.4

    def serve_crossing(self, light_phase_controller, crossing_length, monitor):
        while True:
            phase = yield light_phase_controller.phase_changed_event
            if phase is not LightPhase.PEDESTRIANS:
                continue
            ready = [participant for participant in self.queue.items if participant.queue_entered_at is not None and participant.queue_entered_at < self.env.now]
            if not ready:
                continue
            group = []
            for _ in ready:
                group.append((yield self.queue.get()))
            for pedestrian in group:
                pedestrian.crossing_started_at = float(self.env.now)
                print(f"time={self.env.now:.3f}, id={pedestrian.id}, kind={pedestrian.kind.value}, crossing_started")
            monitor()
            yield self.env.timeout(group[0].duration(crossing_length))
            for pedestrian in group:
                pedestrian.route_finished_event.succeed()


@dataclass(frozen=True)
class MonitoringSnapshot:
    time: float
    outside_queue_len: int
    approach_occupied_count: int
    stop_line_queue_len: int
    pedestrian_queue_len: int


@dataclass
class Journal:
    participants: list[Participant] = field(default_factory=list)
    monitoring: list[MonitoringSnapshot] = field(default_factory=list)
    finished_at: float = 0.0

    def count(self, kind: Kind) -> int:
        return sum(p.kind == kind for p in self.participants)

    def count_finished(self) -> int:
        return sum(p.finished_at is not None for p in self.participants)

    def monitor(
        self,
        *,
        time: float,
        outside_queue_len: int,
        approach_occupied_count: int,
        stop_line_queue_len: int,
        pedestrian_queue_len: int,
    ) -> None:
        snapshot = MonitoringSnapshot(
            time=time,
            outside_queue_len=outside_queue_len,
            approach_occupied_count=approach_occupied_count,
            stop_line_queue_len=stop_line_queue_len,
            pedestrian_queue_len=pedestrian_queue_len,
        )
        if self.monitoring and self.monitoring[-1].time == time:
            self.monitoring[-1] = snapshot
        else:
            self.monitoring.append(snapshot)



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
        self.phase = LightPhase.VEHICLES
        self.phase_ends_at = float(env.now) + 20
        self.phase_changed_event = env.event()

    def run(self):
        phases = ((LightPhase.VEHICLES, 20), (LightPhase.PEDESTRIANS, 10))
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
        is_pedestrian_at_crossing: bool = False,
        capacity_count: int = 5,
    ) -> None:
        lengths = (
            intersection_approach_length,
            pedestrian_approach_length,
            car_crossing_length,
            pedestrian_crossing_length,
        )
        if horizon_ms <= 0 or any(length <= 0 for length in lengths):
            raise ValueError("Параметры времени и расстояния должны быть положительными")
        if capacity_count <= 0:
            raise ValueError("Вместимость подъезда должна быть положительной")
        self.env = env
        self.journal = Journal()
        self.seed = seed
        self.horizon_ms = horizon_ms
        self.car_intersection_approach_length = intersection_approach_length
        self.pedestrian_approach_length = pedestrian_approach_length
        self.car_crossing_length = car_crossing_length
        self.pedestrian_crossing_length = pedestrian_crossing_length
        self.car_arrivals = None if car_arrivals is None else tuple(car_arrivals)
        self.pedestrian_arrivals = None if pedestrian_arrivals is None else tuple(pedestrian_arrivals)
        for arrivals in (self.car_arrivals, self.pedestrian_arrivals):
            if arrivals is not None and any(time < 0 for time in arrivals):
                raise ValueError("Время появления не может быть отрицательным")
        self.is_pedestrian_at_crossing = is_pedestrian_at_crossing
        self.capacity_count = capacity_count
        self.free_places_at_end_count: float | None = None

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
        free_places = simpy.Container(self.env, capacity=self.capacity_count, init=self.capacity_count)
        light_phase_controller = PhaseController(self.env)
        participant_processes: list[simpy.Process] = []
        outside_waiting_count = 0
        occupied_count = 0

        def monitor() -> None:
            self.journal.monitor(
                time=self.now(),
                outside_queue_len=outside_waiting_count,
                approach_occupied_count=occupied_count,
                stop_line_queue_len=len(car_queue.items),
                pedestrian_queue_len=len(pedestrian_queue.items),
            )

        def spawn(kind: Kind) -> None:
            nonlocal outside_waiting_count
            participant_id = self.journal.count(kind) + 1
            queue = car_queue if kind is Kind.CAR else pedestrian_queue
            participant_type = Car if kind is Kind.CAR else Pedestrian
            participant = participant_type(self.env, queue, participant_id, self.now())
            self.journal.participants.append(participant)
            if participant_id == 1:
                if kind is Kind.CAR:
                    self.env.process(participant.serve_crossing(light_phase_controller, self.car_crossing_length, release_place, monitor))
                else:
                    self.env.process(participant.serve_crossing(light_phase_controller, self.pedestrian_crossing_length, monitor))
            print(f"time={self.now():.3f}, id={participant.id}, kind={participant.kind.value}, appeared")
            if kind is Kind.CAR:
                outside_waiting_count += 1
                participant_processes.append(self.env.process(participant.run(self.car_intersection_approach_length, monitor)))
                outside_queue.put(participant)
                monitor()
            else:
                distance = 0 if self.is_pedestrian_at_crossing else self.pedestrian_approach_length
                participant_processes.append(self.env.process(participant.run(distance, monitor)))

        def admit_cars():
            nonlocal outside_waiting_count, occupied_count
            while True:
                car = yield outside_queue.get()
                yield free_places.get(1)
                outside_waiting_count -= 1
                occupied_count += 1
                car.entered_approach_at = self.now()
                print(f"time={self.now():.3f}, id={car.id}, kind={car.kind.value}, approach_entered")
                monitor()
                car.admitted.succeed()

        def release_place():
            nonlocal occupied_count
            occupied_count -= 1
            yield free_places.put(1)

        sources = []
        for kind, arrivals, rate, stream_seed in (
            (Kind.CAR, self.car_arrivals, 360, self.seed),
            (Kind.PEDESTRIAN, self.pedestrian_arrivals, 180, self.seed + 1),
        ):
            sources.append(self.env.process(self.source(kind, arrivals, rate, stream_seed, spawn)))

        self.env.process(light_phase_controller.run())
        self.env.process(admit_cars())
        monitor()
        self.env.run(until=simpy.AllOf(self.env, sources))
        self.env.run(until=simpy.AllOf(self.env, participant_processes))
        self.free_places_at_end_count = free_places.level
        self.journal.finished_at = self.now()
        monitor()
        return self.journal


def main() -> None:
    result = FiniteApproachSimulation(env=simpy.Environment(), car_arrivals=[0] * 8, pedestrian_arrivals=[1, 1], is_pedestrian_at_crossing=True).run()
    for participant in result.participants:
        print(f"id={participant.id}, kind={participant.kind.value}, entered_approach_at={participant.entered_approach_at}, queue_entered_at={participant.queue_entered_at}, crossing_started_at={participant.crossing_started_at}, crossing_finished_at={participant.crossing_finished_at}")


if __name__ == "__main__":
    main()

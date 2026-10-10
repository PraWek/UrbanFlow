"""Автомобильная и пешеходная FIFO-очереди у регулируемого перехода."""

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Any, Callable, Generator

import simpy
from simpy import Environment, Timeout


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
    queue_entered_at: float | None = None
    crossing_started_at: float | None = None
    crossing_finished_at: float | None = None

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
        self.queue_entered_at = None
        self.crossing_started_at = None
        self.crossing_finished_at = None

    def crossing_duration(self, distance: float):
        return distance / self.speed

    def may_start(
        self,
        crossing_distance: float,
        phase_ends_at: float,
    ) -> bool:
        return (
            self.env.now + self.crossing_duration(crossing_distance) <= phase_ends_at + 1e-9
        )

    def approach(self, distance: float):
        yield self.env.timeout(distance / self.speed)
        self.queue_entered_at = float(self.env.now)
        print(f"time={self.env.now:.3f}, id={self.id}, kind={self.kind.value}, queued")
        yield self.queue.put(self)

    def finish(self) -> None:
        self.crossing_finished_at = float(self.env.now)
        print(f"time={self.env.now:.3f}, id={self.id}, kind={self.kind.value}, finished")


@dataclass
class Journal:
    participants: list[Participant] = field(default_factory=list)
    finished_at: float = 0.0


def poisson_source(
    env: simpy.Environment,
    kind: Kind,
    rate_per_hour: float,
    horizon_ms: float,
    rng: random.Random,
    spawn: Callable[..., None],
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
    spawn: Callable[..., None]
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


class SignalizedCrossingSimulation:
    def __init__(
        self,
        *,
        env,
        seed: int = 42,
        horizon_ms: float = 600,
        intersection_approach_length: float = 150,
        pedestrian_approach_length: float = 28,
        car_crossing_length: float = 30,
        pedestrian_crossing_length: float = 7,
        car_arrivals: Iterable[float] | None = None,
        pedestrian_arrivals: Iterable[float] | None = None,
        cars_at_stop_line: bool = False,
        pedestrians_at_crossing: bool = False,
    ) -> None:
        self.env = env
        self.journal = Journal()

        self.seed = seed
        if horizon_ms <= 0:
            raise ValueError("Горизонт генерации должен быть положительным")
        if intersection_approach_length <= 0:
            raise ValueError("Длина подъезда к перекрёстку должна быть положительной")
        if pedestrian_approach_length <= 0:
            raise ValueError("Длина подхода пешехода должна быть положительной")
        if car_crossing_length <= 0:
            raise ValueError("Длина проезда автомобиля должна быть положительной")
        if pedestrian_crossing_length <= 0:
            raise ValueError("Длина пешеходного перехода должна быть положительной")
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
        self.cars_at_stop_line = cars_at_stop_line
        self.pedestrians_at_crossing = pedestrians_at_crossing

    def now(self) -> float:
        return float(self.env.now)

    def run(self) -> Journal:
        car_queue = simpy.Store(self.env)
        pedestrian_queue = simpy.Store(self.env)
        light_phase_controller = PhaseController(self.env)
        done_event = self.env.event()
        counters = {
            Kind.CAR: 0,
            Kind.PEDESTRIAN: 0,
        }
        completed_participants = 0
        is_input_closed = False

        def spawn(kind: Kind) -> None:
            counters[kind] += 1

            if kind == Kind.CAR:
                participant = Participant(self.env, car_queue, counters[kind], kind, self.now())
                distance = self.intersection_approach_length
            else:
                participant = Participant(self.env, pedestrian_queue, counters[kind], kind, self.now())
                distance = self.pedestrian_approach_length

            self.journal.participants.append(participant)
            print(f"time={self.now():.3f}, id={participant.id}, kind={participant.kind.value}, appeared")

            self.env.process(participant.approach(distance))

        def mark_completed(participant: Participant) -> None:
            nonlocal completed_participants
            participant.finish()
            completed_participants += 1
            if is_input_closed and completed_participants == len(self.journal.participants) and not done_event.triggered:
                done_event.succeed()

        def serve_cars():
            while True:
                car = yield car_queue.get()
                while (
                    light_phase_controller.phase is not Phase.VEHICLES or
                    not self.now() + car.crossing_duration(self.car_crossing_length) <= light_phase_controller.phase_ends_at + 1e-9
                ):
                    yield light_phase_controller.phase_changed_event

                car.crossing_started_at = self.now()
                print(f"time={self.now():.3f}, id={car.id}, kind={car.kind.value}, crossing_started")

                yield self.env.timeout(car.crossing_duration(self.car_crossing_length))
                mark_completed(car)


        def serve_pedestrians():
            while True:
                phase = yield light_phase_controller.phase_changed_event
                if phase is not Phase.PEDESTRIANS:
                    continue
                ready = [p for p in pedestrian_queue.items if p.queue_entered_at is not None and p.queue_entered_at < self.now()]
                if not ready:
                    continue
                group = []
                for _ in ready:
                    group.append((yield pedestrian_queue.get()))
                for pedestrian in group:
                    pedestrian.crossing_started_at = self.now()
                    print(f"time={self.now():.3f}, id={pedestrian.id}, kind={pedestrian.kind.value}, event=crossing_started")
                yield self.env.timeout(group[0].crossing_duration(self.pedestrian_crossing_length))
                for pedestrian in group:
                    mark_completed(pedestrian)

        sources = []
        for kind, arrivals, rate, stream_seed in (
            (Kind.CAR, self.car_arrivals, 360, self.seed),
            (Kind.PEDESTRIAN, self.pedestrian_arrivals, 180, self.seed + 1),
        ):
            process = self.env.process(self.source(kind, arrivals, rate, stream_seed, spawn))
            sources.append(process)

        def close_input():
            nonlocal is_input_closed
            yield simpy.AllOf(self.env, sources)
            is_input_closed = True
            if is_input_closed and completed_participants == len(self.journal.participants) and not done_event.triggered:
                done_event.succeed()

        self.env.process(light_phase_controller.run())
        self.env.process(serve_cars())
        self.env.process(serve_pedestrians())
        self.env.process(close_input())
        self.env.run(until=done_event)
        self.journal.finished_at = self.now()
        return self.journal

    def source(self, kind, arrivals, rate, stream_seed, spawn: Callable[..., None]) -> Generator[Timeout, Any, None]:
        if arrivals is not None:
            return scheduled_source(self.env, kind, arrivals, spawn)
        else:
            return poisson_source(self.env, kind, rate, self.horizon_ms, random.Random(stream_seed), spawn)


def main() -> None:
    result = SignalizedCrossingSimulation(
        car_arrivals=[0, 0, 0],
        pedestrian_arrivals=[1, 1],
        cars_at_stop_line=True,
        pedestrians_at_crossing=True,
        env=simpy.Environment()
    ).run()
    for participant in result.participants:
        print(f"id={participant.id}, kind={participant.kind.value}, queue_entered_at={participant.queue_entered_at}, crossing_started_at={participant.crossing_started_at}, crossing_finished_at={participant.crossing_finished_at}")


if __name__ == "__main__":
    main()

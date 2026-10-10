"""Три независимые полосы и согласованные принимающие перекрёстки."""

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable

import simpy


class Kind(str, Enum):
    CAR = "car"
    PEDESTRIAN = "pedestrian"


class Direction(str, Enum):
    STRAIGHT = "straight"
    LEFT = "left"
    RIGHT = "right"


class Phase(str, Enum):
    STRAIGHT = "straight"
    LEFT = "left"
    RIGHT = "right"
    PEDESTRIANS = "pedestrians"
    GREEN = "green"
    RED = "red"


DIRECTIONS = (Direction.STRAIGHT, Direction.LEFT, Direction.RIGHT)
CAPACITIES = {
    Direction.STRAIGHT: 5,
    Direction.LEFT: 3,
    Direction.RIGHT: 2,
}
CENTRAL_PHASES = {
    Direction.STRAIGHT: Phase.STRAIGHT,
    Direction.LEFT: Phase.LEFT,
    Direction.RIGHT: Phase.RIGHT,
}


@dataclass(frozen=True)
class CarArrival:
    time: float
    direction: Direction

    def __post_init__(self) -> None:
        if not isinstance(self.direction, Direction):
            object.__setattr__(self, "direction", Direction(self.direction))


@dataclass(init=False)
class Participant:
    env: simpy.Environment
    queue: simpy.Store
    id: str
    kind: Kind
    speed: float
    appeared_at: float
    direction: Direction | None = None
    central_queue_entered_at: float | None = None
    central_started_at: float | None = None
    central_finished_at: float | None = None
    receiver_arrived_at: float | None = None
    receiver_started_at: float | None = None
    finished_at: float | None = None
    capacity_blocked_time: float = 0.0
    initial: bool = False

    def __init__(
        self,
        env: simpy.Environment,
        queue: simpy.Store,
        id: int | str,
        kind: Kind,
        appeared_at: float,
        direction: Direction | None = None,
        initial: bool = False,
    ) -> None:
        self.env = env
        self.queue = queue
        self.id = f"{kind.value}-{id:04d}" if isinstance(id, int) else id
        self.kind = kind
        self.speed = 15 if kind is Kind.CAR else 1.4
        self.appeared_at = appeared_at
        self.direction = direction
        self.central_queue_entered_at = None
        self.central_started_at = None
        self.central_finished_at = None
        self.receiver_arrived_at = None
        self.receiver_started_at = None
        self.finished_at = None
        self.capacity_blocked_time = 0.0
        self.initial = initial

    def travel(self, distance: float):
        yield self.env.timeout(distance / self.speed)

    def approach(self, distance: float):
        yield from self.travel(distance)
        self.central_queue_entered_at = float(self.env.now)
        print(f"time={self.env.now:.3f}, id={self.id}, kind={self.kind.value}, central_queued")
        yield self.queue.put(self)

    def crossing_duration(self, distance: float) -> float:
        return distance / self.speed

    def may_start(self, distance: float, phase_ends_at: float) -> bool:
        return self.env.now + self.crossing_duration(distance) <= phase_ends_at + 1e-9

    def finish(self) -> None:
        self.finished_at = float(self.env.now)
        print(f"time={self.env.now:.3f}, id={self.id}, kind={self.kind.value}, finished")


@dataclass
class Journal:
    participants: list[Participant] = field(default_factory=list)
    monitoring: list[dict] = field(default_factory=list)
    finished_at: float = 0.0

    def completed_by_direction(self) -> dict[Direction, int]:
        return {
            direction: sum(
                participant.kind is Kind.CAR
                and participant.direction is direction
                and participant.finished_at is not None
                for participant in self.participants
            )
            for direction in DIRECTIONS
        }


def poisson_source(
    env: simpy.Environment,
    rate_per_hour: float,
    horizon_ms: float,
    rng: random.Random,
    spawn: Callable[[], None],
):
    rate_per_second = rate_per_hour / 3600
    while True:
        interval = rng.expovariate(rate_per_second)
        if env.now + interval >= horizon_ms:
            yield env.timeout(horizon_ms - env.now)
            return
        yield env.timeout(interval)
        spawn()


def scheduled_car_source(
    env: simpy.Environment,
    arrivals: tuple[CarArrival, ...],
    spawn: Callable[[Direction], None],
):
    for arrival in sorted(arrivals, key=lambda item: item.time):
        yield env.timeout(arrival.time - env.now)
        spawn(arrival.direction)


def scheduled_source(
    env: simpy.Environment,
    arrivals: tuple[float, ...],
    spawn: Callable[[], None],
):
    for arrival in sorted(arrivals):
        yield env.timeout(arrival - env.now)
        spawn()


class PhaseController:
    def __init__(
        self,
        env: simpy.Environment,
        name: str,
        phases: tuple[tuple[Phase, float], ...],
    ) -> None:
        self.env = env
        self.name = name
        self.phases = phases
        self.phase = phases[0][0]
        self.phase_ends_at = float(env.now) + phases[0][1]
        self.phase_changed_event = env.event()

    def run(self):
        index = 0
        print(f"time={self.env.now:.3f}, signal={self.name}, phase={self.phase.value}")
        while True:
            yield self.env.timeout(self.phases[index][1])
            index = (index + 1) % len(self.phases)
            self.phase = self.phases[index][0]
            self.phase_ends_at = float(self.env.now) + self.phases[index][1]
            previous_event = self.phase_changed_event
            self.phase_changed_event = self.env.event()
            print(f"time={self.env.now:.3f}, signal={self.name}, phase={self.phase.value}")
            previous_event.succeed(self.phase)


class CoordinatedCorridorSimulation:
    def __init__(
        self,
        *,
        env: simpy.Environment,
        seed: int = 42,
        horizon_ms: float = 600,
        intersection_approach_length: float = 150,
        pedestrian_approach_length: float = 28,
        central_crossing_length: float = 30,
        pedestrian_crossing_length: float = 7,
        receiver_approach_length: float = 150,
        receiver_crossing_length: float = 30,
        car_arrivals: Iterable[CarArrival] | None = None,
        pedestrian_arrivals: Iterable[float] | None = None,
        cars_at_stop_line: bool = False,
        pedestrians_at_crossing: bool = False,
        prefilled_left: int = 0,
        left_release_blocked_until: float = 0,
    ) -> None:
        lengths = (
            intersection_approach_length,
            pedestrian_approach_length,
            central_crossing_length,
            pedestrian_crossing_length,
            receiver_approach_length,
            receiver_crossing_length,
        )
        if horizon_ms <= 0 or any(length <= 0 for length in lengths):
            raise ValueError("Параметры времени и расстояния должны быть положительными")
        if left_release_blocked_until < 0:
            raise ValueError("Время блокировки не может быть отрицательным")
        if prefilled_left not in range(CAPACITIES[Direction.LEFT] + 1):
            raise ValueError("Предзаполнение левого подхода превышает вместимость")
        self.env = env
        self.journal = Journal()
        self.seed = seed
        self.horizon_ms = horizon_ms
        self.intersection_approach_length = intersection_approach_length
        self.pedestrian_approach_length = pedestrian_approach_length
        self.central_crossing_length = central_crossing_length
        self.pedestrian_crossing_length = pedestrian_crossing_length
        self.receiver_approach_length = receiver_approach_length
        self.receiver_crossing_length = receiver_crossing_length
        self.car_arrivals = None if car_arrivals is None else tuple(car_arrivals)
        self.pedestrian_arrivals = None if pedestrian_arrivals is None else tuple(pedestrian_arrivals)
        if self.car_arrivals is not None and any(arrival.time < 0 for arrival in self.car_arrivals):
            raise ValueError("Появление автомобиля задано неверно")
        if self.pedestrian_arrivals is not None and any(time < 0 for time in self.pedestrian_arrivals):
            raise ValueError("Время появления не может быть отрицательным")
        self.cars_at_stop_line = cars_at_stop_line
        self.pedestrians_at_crossing = pedestrians_at_crossing
        self.prefilled_left = prefilled_left
        self.left_release_blocked_until = left_release_blocked_until
        self.free_places_at_end: dict[str, float] = {}

    def now(self) -> float:
        return float(self.env.now)

    def run(self) -> Journal:
        central_queues = {direction: simpy.Store(self.env) for direction in DIRECTIONS}
        receiver_queues = {direction: simpy.Store(self.env) for direction in DIRECTIONS}
        pedestrian_queue = simpy.Store(self.env)
        free_places = {
            direction: simpy.Container(self.env, capacity=capacity, init=capacity)
            for direction, capacity in CAPACITIES.items()
        }
        holders: dict[Direction, dict[str, str]] = {direction: {} for direction in DIRECTIONS}
        capacity_changed_events = {direction: self.env.event() for direction in DIRECTIONS}
        central_signal = PhaseController(
            self.env,
            "central",
            ((Phase.STRAIGHT, 24), (Phase.LEFT, 12), (Phase.RIGHT, 12), (Phase.PEDESTRIANS, 12)),
        )
        receiver_signals = {
            Direction.STRAIGHT: PhaseController(self.env, "receiver_straight", ((Phase.RED, 12), (Phase.GREEN, 24), (Phase.RED, 24))),
            Direction.LEFT: PhaseController(self.env, "receiver_left", ((Phase.RED, 36), (Phase.GREEN, 12), (Phase.RED, 12))),
            Direction.RIGHT: PhaseController(self.env, "receiver_right", ((Phase.RED, 48), (Phase.GREEN, 12))),
        }
        done_event = self.env.event()
        counters = {Kind.CAR: 0, Kind.PEDESTRIAN: 0}
        route_rng = random.Random(self.seed + 2)
        completed_participants = 0
        is_input_closed = False

        def monitor() -> None:
            row: dict[str, float | int] = {
                "time": self.now(),
                "pedestrian_queue": len(pedestrian_queue.items),
            }
            for direction in DIRECTIONS:
                name = direction.value
                reserved = sum(state == "reserved" for state in holders[direction].values())
                occupied = sum(state == "occupied" for state in holders[direction].values())
                row[f"central_queue_{name}"] = len(central_queues[direction].items)
                row[f"receiver_queue_{name}"] = len(receiver_queues[direction].items)
                row[f"receiver_reserved_{name}"] = reserved
                row[f"receiver_occupied_{name}"] = occupied
                row[f"receiver_used_{name}"] = reserved + occupied
            if self.journal.monitoring and self.journal.monitoring[-1]["time"] == self.env.now:
                self.journal.monitoring[-1] = row
            else:
                self.journal.monitoring.append(row)

        def notify_capacity(direction: Direction) -> None:
            previous_event = capacity_changed_events[direction]
            capacity_changed_events[direction] = self.env.event()
            if not previous_event.triggered:
                previous_event.succeed()

        def maybe_finish() -> None:
            if is_input_closed and completed_participants == len(self.journal.participants) and not done_event.triggered:
                done_event.succeed()

        def mark_completed(participant: Participant) -> None:
            nonlocal completed_participants
            participant.finish()
            completed_participants += 1
            monitor()
            maybe_finish()

        def choose_direction() -> Direction:
            value = route_rng.random()
            if value < 0.5:
                return Direction.STRAIGHT
            if value < 0.8:
                return Direction.LEFT
            return Direction.RIGHT

        def spawn_car(direction: Direction | None = None) -> None:
            counters[Kind.CAR] += 1
            selected_direction = direction or choose_direction()
            participant = Participant(self.env, central_queues[selected_direction], counters[Kind.CAR], Kind.CAR, self.now(), selected_direction)
            self.journal.participants.append(participant)
            print(f"time={self.now():.3f}, id={participant.id}, kind={participant.kind.value}, direction={selected_direction.value}, appeared")
            distance = 0 if self.cars_at_stop_line else self.intersection_approach_length
            self.env.process(participant.approach(distance))

        def spawn_pedestrian() -> None:
            counters[Kind.PEDESTRIAN] += 1
            participant = Participant(self.env, pedestrian_queue, counters[Kind.PEDESTRIAN], Kind.PEDESTRIAN, self.now())
            self.journal.participants.append(participant)
            print(f"time={self.now():.3f}, id={participant.id}, kind={participant.kind.value}, appeared")
            distance = 0 if self.pedestrians_at_crossing else self.pedestrian_approach_length
            self.env.process(participant.approach(distance))

        def prefill_left_approach():
            for number in range(1, self.prefilled_left + 1):
                yield free_places[Direction.LEFT].get(1)
                participant = Participant(self.env, receiver_queues[Direction.LEFT], f"initial-left-{number:03d}", Kind.CAR, 0.0, Direction.LEFT, True)
                participant.receiver_arrived_at = 0.0
                self.journal.participants.append(participant)
                holders[Direction.LEFT][participant.id] = "occupied"
                yield receiver_queues[Direction.LEFT].put(participant)
                print(f"time={self.now():.3f}, id={participant.id}, kind={participant.kind.value}, direction={participant.direction.value}, receiver_prefilled")
                monitor()

        def travel_to_receiver(participant: Participant):
            direction = participant.direction
            holders[direction][participant.id] = "occupied"
            monitor()
            yield from participant.travel(self.receiver_approach_length)
            participant.receiver_arrived_at = self.now()
            print(f"time={self.now():.3f}, id={participant.id}, kind={participant.kind.value}, direction={direction.value}, receiver_queued")
            yield receiver_queues[direction].put(participant)
            monitor()

        def serve_central(direction: Direction):
            while True:
                participant = yield central_queues[direction].get()
                while True:
                    if central_signal.phase is not CENTRAL_PHASES[direction] or not participant.may_start(self.central_crossing_length, central_signal.phase_ends_at):
                        yield central_signal.phase_changed_event
                        continue
                    if free_places[direction].level < 1:
                        wait_started = self.now()
                        yield simpy.AnyOf(self.env, [central_signal.phase_changed_event, capacity_changed_events[direction]])
                        participant.capacity_blocked_time += self.now() - wait_started
                        continue
                    yield free_places[direction].get(1)
                    holders[direction][participant.id] = "reserved"
                    monitor()
                    break
                participant.central_started_at = self.now()
                print(f"time={self.now():.3f}, id={participant.id}, kind={participant.kind.value}, direction={direction.value}, central_started")
                yield self.env.timeout(participant.crossing_duration(self.central_crossing_length))
                participant.central_finished_at = self.now()
                print(f"time={self.now():.3f}, id={participant.id}, kind={participant.kind.value}, direction={direction.value}, central_finished")
                self.env.process(travel_to_receiver(participant))

        def serve_receiver(direction: Direction):
            while True:
                participant = yield receiver_queues[direction].get()
                while True:
                    if direction is Direction.LEFT and self.env.now < self.left_release_blocked_until:
                        yield self.env.timeout(self.left_release_blocked_until - self.env.now)
                        continue
                    controller = receiver_signals[direction]
                    if controller.phase is not Phase.GREEN or not participant.may_start(self.receiver_crossing_length, controller.phase_ends_at):
                        yield controller.phase_changed_event
                        continue
                    break
                participant.receiver_started_at = self.now()
                print(f"time={self.now():.3f}, id={participant.id}, kind={participant.kind.value}, direction={direction.value}, receiver_started")
                yield self.env.timeout(participant.crossing_duration(self.receiver_crossing_length))
                holders[direction].pop(participant.id)
                yield free_places[direction].put(1)
                notify_capacity(direction)
                mark_completed(participant)

        def serve_pedestrians():
            while True:
                phase = yield central_signal.phase_changed_event
                if phase is not Phase.PEDESTRIANS:
                    continue
                ready = [participant for participant in pedestrian_queue.items if participant.central_queue_entered_at is not None and participant.central_queue_entered_at < self.now()]
                if not ready:
                    continue
                group = []
                for _ in ready:
                    group.append((yield pedestrian_queue.get()))
                for pedestrian in group:
                    pedestrian.central_started_at = self.now()
                    print(f"time={self.now():.3f}, id={pedestrian.id}, kind={pedestrian.kind.value}, central_started")
                monitor()
                yield self.env.timeout(group[0].crossing_duration(self.pedestrian_crossing_length))
                for pedestrian in group:
                    pedestrian.central_finished_at = self.now()
                    mark_completed(pedestrian)

        sources = [self.env.process(prefill_left_approach())]
        if self.car_arrivals is None:
            sources.append(self.env.process(poisson_source(self.env, 360, self.horizon_ms, random.Random(self.seed), lambda: spawn_car())))
        else:
            sources.append(self.env.process(scheduled_car_source(self.env, self.car_arrivals, spawn_car)))
        if self.pedestrian_arrivals is None:
            sources.append(self.env.process(poisson_source(self.env, 180, self.horizon_ms, random.Random(self.seed + 1), spawn_pedestrian)))
        else:
            sources.append(self.env.process(scheduled_source(self.env, self.pedestrian_arrivals, spawn_pedestrian)))

        def close_input():
            nonlocal is_input_closed
            yield simpy.AllOf(self.env, sources)
            is_input_closed = True
            maybe_finish()

        self.env.process(central_signal.run())
        for controller in receiver_signals.values():
            self.env.process(controller.run())
        for direction in DIRECTIONS:
            self.env.process(serve_central(direction))
            self.env.process(serve_receiver(direction))
        self.env.process(serve_pedestrians())
        self.env.process(close_input())
        monitor()
        self.env.run(until=done_event)
        self.free_places_at_end = {direction.value: container.level for direction, container in free_places.items()}
        self.journal.finished_at = self.now()
        monitor()
        return self.journal


def main() -> None:
    result = CoordinatedCorridorSimulation(env=simpy.Environment(), car_arrivals=[CarArrival(0, Direction.STRAIGHT), CarArrival(0, Direction.LEFT), CarArrival(0, Direction.RIGHT)], pedestrian_arrivals=[], cars_at_stop_line=True).run()
    for participant in result.participants:
        direction = participant.direction.value if participant.direction is not None else None
        print(f"id={participant.id}, kind={participant.kind.value}, direction={direction}, central_started_at={participant.central_started_at}, receiver_arrived_at={participant.receiver_arrived_at}, receiver_started_at={participant.receiver_started_at}, finished_at={participant.finished_at}")


if __name__ == "__main__":
    main()

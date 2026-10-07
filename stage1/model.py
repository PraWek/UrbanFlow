"""
Общая учебная модель для упражнений 4–7

Процессы допуска, обслуживания и движения разделены. Ожидание места
за переходом никогда не занимает сам переход
"""

import random

import simpy

from .data import Participant, Result
from .flows import poisson_source, scheduled_source
from .signals import Signal, receiver_phases


ROUTES = ("straight", "left", "right")
CAPACITIES = {"straight": 5, "left": 3, "right": 2}
LOCAL_WINDOWS = {"straight": (12, 36), "left": (36, 48), "right": (48, 60)}


class StreetModel:
    def __init__(self, exercise, *, seed=42, cars=None, pedestrians=None,
                 cars_at_stop=False, pedestrians_at_crossing=False,
                 blocked_until=0, initial_left=0, horizon=600,
                 scenario="random"):
        if exercise not in (4, 5, 6, 7):
            raise ValueError("Общая модель реализует упражнения 4–7")
        if horizon <= 0 or blocked_until < 0:
            raise ValueError("Горизонт должен быть положительным, запрет неотрицательным")
        if initial_left not in range(4) or (initial_left and exercise != 7):
            raise ValueError("Предзаполнение B_L: от 0 до 3, только для упражнения 7")
        if cars_at_stop and exercise == 5:
            raise ValueError("В упражнении 5 автомобили должны въезжать через участок A")
        for arrivals in (cars, pedestrians):
            if arrivals is not None and any(a.time < 0 or a.route not in ROUTES
                                             for a in arrivals):
                raise ValueError("Время появления неотрицательно; направление неизвестно")
        self.env = simpy.Environment()
        self.result = Result(exercise, scenario)
        self.exercise = exercise
        self.done = self.env.event()
        self.input_closed = False
        self.finished_count = 0
        self.cars_at_stop = cars_at_stop
        self.pedestrians_at_crossing = pedestrians_at_crossing
        self.blocked_until = blocked_until
        self.route_rng = random.Random(seed + 2)
        self.ids = {"car": 0, "pedestrian": 0}
        self.routes = ROUTES if exercise == 7 else ("straight",)
        self.car_queues = {r: simpy.Store(self.env) for r in self.routes}
        self.car_waiting = dict.fromkeys(self.routes, 0)
        self.ped_queue = simpy.Store(self.env)
        self.external = simpy.Store(self.env)
        self.external_waiting = 0
        self.a_used = 0
        self.free_a = simpy.Container(self.env, capacity=5, init=5) if exercise == 5 else None
        self.capacities = (CAPACITIES if exercise == 7 else
                           {"straight": 5} if exercise == 6 else {})
        self.free_b = {
            r: simpy.Container(self.env, capacity=n, init=n)
            for r, n in self.capacities.items()
        }
        self.holders = {r: {} for r in self.capacities}
        self.b_queues = {r: simpy.Store(self.env) for r in self.capacities}
        self.b_waiting = dict.fromkeys(self.capacities, 0)
        phases = (("straight", 24), ("left", 12), ("right", 12), ("pedestrian", 12))
        if exercise != 7:
            phases = (("straight", 20), ("pedestrian", 10))
        self.signal = Signal(self.env, phases, self.result, "central")
        self.local_signals = {
            r: Signal(self.env, receiver_phases(*LOCAL_WINDOWS[r]), self.result, f"B_{r}")
            for r in self.routes if exercise == 7
        }
        # Resource ограничивает пользователей перехода, Container - места на дороге
        self.crossings = {r: simpy.Resource(self.env, capacity=1) for r in self.routes}
        for r in self.routes:
            self.env.process(self.serve_cars(r))
        for r in self.capacities:
            self.env.process(self.serve_receiver(r))
        self.env.process(self.serve_pedestrians())
        if self.free_a is not None:
            self.env.process(self.admit())
        if initial_left:
            self.env.process(self.prefill_left(initial_left))
        sources = []
        for kind, arrivals, rate, stream_seed in (
            ("car", cars, 360, seed), ("pedestrian", pedestrians, 180, seed + 1)
        ):
            if arrivals is None:
                generator = poisson_source(
                    self.env, rate, horizon, random.Random(stream_seed),
                    lambda kind=kind: self.spawn(kind),
                )
            else:
                generator = scheduled_source(
                    self.env, arrivals, lambda route, kind=kind: self.spawn(kind, route)
                )
            sources.append(self.env.process(generator))
        self.env.process(self.close_input(sources))

    def snapshot(self):
        row = {
            "time": float(self.env.now), "external_queue": self.external_waiting,
            "a_occupied": self.a_used, "pedestrian_queue": len(self.ped_queue.items),
        }
        for r in self.routes:
            row[f"queue_{r}"] = self.car_waiting[r]
        for r, holders in self.holders.items():
            reserved = sum(state == "reserved" for state in holders.values())
            row[f"b_{r}_reserved"] = reserved
            row[f"b_{r}_occupied"] = len(holders) - reserved
            row[f"b_{r}_used"] = len(holders)
            row[f"b_{r}_queue"] = self.b_waiting[r]
            if len(holders) > self.capacities[r]:
                raise RuntimeError("Превышена вместимость принимающего участка")
        if self.free_a is not None and self.a_used > 5:
            raise RuntimeError("Превышена вместимость A")
        # Несколько callbacks в один момент времени не образуют физическую
        # очередь: сохраняем итоговое состояние этого момента, журнал — полный
        if self.result.monitoring and self.result.monitoring[-1]["time"] == row["time"]:
            self.result.monitoring[-1] = row
        else:
            self.result.monitoring.append(row)

    def log(self, participant, event):
        self.result.log(self.env.now, participant.id, event,
                        kind=participant.kind, route=participant.route)
        self.snapshot()

    def spawn(self, kind, route=None):
        self.ids[kind] += 1
        if kind == "car" and route is None:
            route = (self.route_rng.choices(ROUTES, weights=(0.5, 0.3, 0.2))[0]
                     if self.exercise == 7 else "straight")
        if self.exercise != 7:
            route = "straight"
        participant = Participant(f"{kind}-{self.ids[kind]:03d}", kind,
                                  float(self.env.now), route or "straight")
        self.result.records.append(participant)
        self.log(participant, "appeared")
        if kind == "pedestrian":
            self.env.process(self.approach_pedestrian(participant))
        elif self.free_a is not None:
            self.external_waiting += 1
            self.external.put(participant)
            self.snapshot()
        else:
            self.env.process(self.approach_car(participant))

    def admit(self):
        while True:
            participant = yield self.external.get()
            # Выбранный участник всё ещё учитывается во внешней очереди
            yield self.free_a.get(1)
            self.external_waiting -= 1
            self.env.process(self.approach_car(participant))

    def approach_car(self, participant):
        participant.entered_a = float(self.env.now)
        self.a_used += 1
        self.log(participant, "entered_a")
        yield self.env.timeout(0 if self.cars_at_stop else 150 / 15)
        participant.queued = float(self.env.now)
        self.car_waiting[participant.route] += 1
        self.car_queues[participant.route].put(participant)
        self.log(participant, "queued")

    def approach_pedestrian(self, participant):
        self.log(participant, "walk_start")
        yield self.env.timeout(0 if self.pedestrians_at_crossing else 28 / 1.4)
        participant.queued = float(self.env.now)
        self.ped_queue.put(participant)
        self.log(participant, "queued")

    def reserve(self, participant, route):
        """
        Повторная проверка сигнала после каждой попытки получить место.

        Заявка ожидает либо место, либо смену сигнала. При потере разрешения
        заявка отменяется, а уже полученное место возвращается
        """
        while True:
            while not self.signal.permits(route, 2):
                yield self.signal.changed
            if route not in self.free_b:
                return
            request = self.free_b[route].get(1)
            waiting_since = float(self.env.now)
            was_full = not request.triggered
            yield request | self.signal.changed
            if was_full:
                participant.blocked_b += self.env.now - waiting_since
            if request.triggered:
                if self.signal.permits(route, 2):
                    self.holders[route][participant.id] = "reserved"
                    self.log(participant, "reserved_b")
                    return
                yield self.free_b[route].put(1)
                self.log(participant, "returned_reservation")
            else:
                request.cancel()
                self.log(participant, "cancelled_reservation")

    def serve_cars(self, route):
        while True:
            participant = yield self.car_queues[route].get()
            yield self.env.process(self.reserve(participant, route))
            with self.crossings[route].request() as request:
                yield request
                # Resource выдаётся сразу: один процесс обслуживания на направление
                if not self.signal.permits(route, 2):
                    raise RuntimeError("Разрешение потеряно перед стартом")
                participant.start = float(self.env.now)
                self.car_waiting[route] -= 1
                self.log(participant, "cross_start")
                yield self.env.timeout(2)
                participant.end = float(self.env.now)
                self.a_used -= 1
                if route in self.holders:
                    self.holders[route][participant.id] = "on_b"
                self.log(participant, "cross_end")
                if self.free_a is not None:
                    yield self.free_a.put(1)
                if route in self.free_b:
                    self.env.process(self.drive_b(participant))
                else:
                    self.finish(participant)

    def serve_pedestrians(self):
        while True:
            allowed = yield self.signal.changed
            if allowed != "pedestrian":
                continue
            # Прибытие ровно в начале интервала относится к следующему циклу
            batch = [p for p in self.ped_queue.items if p.queued < self.env.now]
            for participant in batch:
                received = yield self.ped_queue.get()
                if received is not participant:
                    raise RuntimeError("Нарушен FIFO пешеходной очереди")
                participant.start = float(self.env.now)
                self.log(participant, "cross_start")
            if batch:
                yield self.env.timeout(7 / 1.4)
                for participant in batch:
                    participant.end = float(self.env.now)
                    self.log(participant, "cross_end")
                    self.finish(participant)

    def drive_b(self, participant):
        yield self.env.timeout(10)
        participant.arrived_b = float(self.env.now)
        route = participant.route
        self.holders[route][participant.id] = "queued_b"
        self.b_waiting[route] += 1
        self.b_queues[route].put(participant)
        self.log(participant, "queued_b")

    def serve_receiver(self, route):
        while True:
            participant = yield self.b_queues[route].get()
            blocked = self.blocked_until if self.exercise == 6 or route == "left" else 0
            if self.env.now < blocked:
                yield self.env.timeout(blocked - self.env.now)
            if self.exercise == 7:
                signal = self.local_signals[route]
                while not signal.permits("green", 2):
                    yield signal.changed
                participant.start_b = float(self.env.now)
                self.b_waiting[route] -= 1
                self.holders[route][participant.id] = "crossing_b"
                self.log(participant, "receiver_start")
                yield self.env.timeout(2)
            else:
                self.b_waiting[route] -= 1
            del self.holders[route][participant.id]
            yield self.free_b[route].put(1)
            self.finish(participant)

    def prefill_left(self, count):
        for index in range(count):
            participant = Participant(f"initial-left-{index + 1}", "car", 0,
                                      "left", arrived_b=0, initial=True)
            self.result.records.append(participant)
            yield self.free_b["left"].get(1)
            self.holders["left"][participant.id] = "queued_b"
            self.b_waiting["left"] += 1
            self.b_queues["left"].put(participant)
            self.log(participant, "initial_b")

    def finish(self, participant):
        participant.exited = float(self.env.now)
        self.finished_count += 1
        self.log(participant, "exited")
        self.check_finished()

    def check_finished(self):
        if self.input_closed and self.finished_count == len(self.result.records):
            if not self.done.triggered:
                self.done.succeed()

    def close_input(self, sources):
        yield self.env.all_of(sources)
        self.input_closed = True
        self.result.log(self.env.now, "sources", "closed")
        self.check_finished()

    def run(self):
        self.env.run(until=self.done)
        self.result.finished_at = float(self.env.now)
        return self.result

"""Независимые входные потоки и движение с постоянной скоростью"""

import random

import simpy

from .data import Participant, Result


def poisson_source(env, rate_per_hour, horizon, rng, spawn):
    """Первый участник тоже появляется после случайного интервала"""
    while True:
        delay = rng.expovariate(rate_per_hour / 3600)
        if env.now + delay >= horizon:
            yield env.timeout(horizon - env.now)
            return
        yield env.timeout(delay)
        spawn()


def scheduled_source(env, arrivals, spawn):
    # Стабильная сортировка: при равном времени порядок совпадает с ID
    for arrival in sorted(arrivals, key=lambda a: a.time):
        yield env.timeout(arrival.time - env.now)
        spawn(arrival.route)


def travel(env, participant, length, speed, result):
    result.log(env.now, participant.id, "travel_start", kind=participant.kind)
    yield env.timeout(length / speed)
    participant.queued = participant.exited = float(env.now)
    result.log(env.now, participant.id, "arrived", kind=participant.kind)


def run_movement(exercise=2, seed=42):
    env = simpy.Environment()
    result = Result(exercise, "deterministic" if exercise == 2 else "random")

    def spawn(kind):
        number = 1 + sum(p.kind == kind for p in result.records)
        participant = Participant(f"{kind}-{number:03d}", kind, float(env.now))
        result.records.append(participant)
        result.log(env.now, participant.id, "appeared", kind=kind)
        length, speed = (150, 15) if kind == "car" else (28, 1.4)
        env.process(travel(env, participant, length, speed, result))

    if exercise == 2:
        spawn("car")
        spawn("pedestrian")
    else:
        env.process(poisson_source(env, 360, 600, random.Random(seed),
                                   lambda: spawn("car")))
        env.process(poisson_source(env, 180, 600, random.Random(seed + 1),
                                   lambda: spawn("pedestrian")))
    env.run()  # Здесь нет бесконечного контроллера
    result.finished_at = float(env.now)
    return result

"""Упражнение 1: девять переключений за 180 секунд"""

import simpy

from .data import Result


def traffic_light(env, green_duration, yellow_duration, red_duration, *, journal=None):
    while True:
        for color, duration in (("green", green_duration), ("yellow", yellow_duration),
                                ("red", red_duration)):
            row = dict(time=float(env.now), actor="traffic_light", event="signal", color=color)
            if journal is not None:
                journal.append(row)
            else:
                print(f"t={env.now:g}: {color}")
            yield env.timeout(duration)


def run():
    env = simpy.Environment()
    result = Result(1, "deterministic")
    env.process(traffic_light(env, 30, 5, 25, journal=result.events))
    env.run(until=180)
    result.finished_at = float(env.now)
    return result


if __name__ == "__main__":
    from .reporting import display
    display(run(), show_log=True)

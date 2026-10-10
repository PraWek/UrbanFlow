"""Циклический светофор как дискретно-событийный процесс."""

import simpy


def traffic_light(
    env: simpy.Environment,
    green_duration: float,
    yellow_duration: float,
    red_duration: float,
):
    """Бесконечно повторяет цикл сигналов и печатает каждое переключение."""
    while True:
        for color, duration in (
            ("green", green_duration),
            ("yellow", yellow_duration),
            ("red", red_duration),
        ):
            print(f"time={env.now:g}, color={color}")
            yield env.timeout(duration)


class TrafficLightSimulation:
    def __init__(
        self,
        green_duration: float = 30,
        yellow_duration: float = 5,
        red_duration: float = 25,
    ) -> None:
        if min(green_duration, yellow_duration, red_duration) <= 0:
            raise ValueError("Длительности сигналов должны быть положительными")
        self.green_duration = green_duration
        self.yellow_duration = yellow_duration
        self.red_duration = red_duration

    def run(self, until: float = 180) -> None:
        if until <= 0:
            raise ValueError("Время моделирования должно быть положительным")
        env = simpy.Environment()
        env.process(
            traffic_light(
                env,
                self.green_duration,
                self.yellow_duration,
                self.red_duration,
            )
        )
        env.run(until=until)


def main() -> None:
    TrafficLightSimulation().run()


if __name__ == "__main__":
    main()

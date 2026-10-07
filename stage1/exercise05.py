"""Упражнение 5: пять мест на A, остальные автомобили ждут снаружи"""

from .data import Arrival
from .model import StreetModel


def run(seed=42):
    return StreetModel(5, seed=seed).run()


def demo():
    return StreetModel(5, cars=[Arrival(0)] * 8, pedestrians=[Arrival(1)] * 2,
                       pedestrians_at_crossing=True, scenario="table").run()


if __name__ == "__main__":
    from .reporting import display
    display(demo(), show_log=True)
    display(run())

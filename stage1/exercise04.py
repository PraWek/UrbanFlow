"""Упражнение 4: регулируемый переход и две FIFO-очереди"""

from .data import Arrival
from .model import StreetModel


def run(seed=42):
    return StreetModel(4, seed=seed).run()


def demo():
    return StreetModel(4, cars=[Arrival(0)] * 3, pedestrians=[Arrival(1)] * 2,
                       cars_at_stop=True, pedestrians_at_crossing=True,
                       scenario="table").run()


if __name__ == "__main__":
    from .reporting import display
    display(demo(), show_log=True)
    display(run())

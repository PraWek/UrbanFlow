"""Упражнение 7: три направления и принимающие перекрёстки B_T/B_L/B_R"""

from .data import Arrival
from .model import StreetModel


def run(seed=42):
    return StreetModel(7, seed=seed).run()


def demo(prefilled=False):
    return StreetModel(
        7, cars=[Arrival(0, route) for route in ("straight", "left", "right")],
        pedestrians=[], cars_at_stop=True, initial_left=3 if prefilled else 0,
        blocked_until=120 if prefilled else 0,
        scenario="prefilled_left" if prefilled else "table",
    ).run()


if __name__ == "__main__":
    from .reporting import display
    display(demo(), show_log=True)
    display(demo(prefilled=True), show_log=True)
    display(run())

"""Упражнение 6: парные запуски с открытым и закрытым выходом B"""

from .data import Arrival
from .model import StreetModel


def run(seed=42, blocked_until=0):
    return StreetModel(6, seed=seed, blocked_until=blocked_until,
                       scenario="blocked" if blocked_until else "open").run()


def compare(seed=42):
    # Раздельные RNG гарантируют одинаковые появления при разных задержках
    return run(seed), run(seed, blocked_until=60)


def demo(blocked_until=60):
    return StreetModel(6, cars=[Arrival(0)] * 8, pedestrians=[Arrival(1)] * 2,
                       cars_at_stop=True, pedestrians_at_crossing=True,
                       blocked_until=blocked_until,
                       scenario="table_blocked" if blocked_until else "table_open").run()


if __name__ == "__main__":
    from .reporting import display
    display(demo(), show_log=True)
    for result in compare():
        display(result)

"""Упражнение 2: одновременное движение автомобиля и пешехода"""

from .flows import run_movement


def run():
    return run_movement(2)


if __name__ == "__main__":
    from .reporting import display
    display(run(), show_log=True)
